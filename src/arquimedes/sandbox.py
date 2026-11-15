"""Run untrusted candidate code outside the main process.

A candidate is generated code and is treated as hostile. The main process
never evaluates it: it only parses it with ``ast`` (which does not run
anything) and then hands it to a short-lived child interpreter.

Layers, from the outside in:

1. static check: no imports, no dunder or frame attributes, no dangerous names;
2. a child ``python -I`` process with an empty environment, a private temporary
   working directory and input/output exchanged only through files there;
3. a wall-clock timeout that kills the child, plus CPU and memory limits where
   the platform offers ``resource``;
4. inside the child, the candidate sees a short allowlist of builtins (no
   ``__import__``, no ``open``) and network-related modules are made
   unimportable;
5. whatever comes back is validated again by the problem's verifier in the
   main process.

This is defence in depth, not a jail. The child still runs with the operating
system privileges of the user. Run it inside a container or VM without network
before feeding it code from a real model. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arquimedes.problema import Problema, SaidaInvalida

OK = "ok"
CODIGO_REJEITADO = "codigo_rejeitado"
TEMPO_ESGOTADO = "tempo_esgotado"
ERRO_EXECUCAO = "erro_execucao"
FORMATO_INVALIDO = "formato_invalido"

TAMANHO_MAXIMO_CODIGO = 20_000

_NOMES_PROIBIDOS = frozenset(
    {
        "eval", "exec", "compile", "open", "input", "breakpoint", "help", "exit", "quit",
        "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir", "type", "object",
        "super", "classmethod", "staticmethod", "property", "memoryview", "id",
    }
)  # fmt: skip

_ATRIBUTOS_PROIBIDOS = frozenset(
    {
        "gi_frame", "gi_code", "gi_yieldfrom", "cr_frame", "cr_code", "cr_await", "ag_frame",
        "ag_code", "ag_await", "tb_frame", "tb_next", "f_back", "f_builtins", "f_code",
        "f_globals", "f_locals", "co_code", "co_consts", "co_names", "func_globals",
        "format", "format_map",
    }
)  # fmt: skip


class CodigoRejeitado(ValueError):
    """The candidate source failed the static check and was never executed."""


@dataclass(frozen=True)
class ResultadoSandbox:
    """Outcome of one candidate run."""

    status: str
    saidas: list[Any] | None = None
    erro: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK


def validar_codigo(codigo: str, nome_funcao: str) -> None:
    """Statically reject source that the sandbox refuses to run.

    Only ``ast.parse`` is used, so nothing in ``codigo`` is executed here.
    """
    if not isinstance(codigo, str):
        raise CodigoRejeitado("candidate must be a string of source code")
    if len(codigo) > TAMANHO_MAXIMO_CODIGO:
        raise CodigoRejeitado(f"candidate is longer than {TAMANHO_MAXIMO_CODIGO} characters")
    try:
        arvore = ast.parse(codigo)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as erro:
        raise CodigoRejeitado(f"candidate does not parse: {type(erro).__name__}") from None

    for no in ast.walk(arvore):
        if isinstance(no, ast.Import | ast.ImportFrom):
            raise CodigoRejeitado("imports are not allowed")
        if isinstance(no, ast.Global | ast.Nonlocal | ast.ClassDef):
            raise CodigoRejeitado(f"{type(no).__name__} is not allowed")
        if isinstance(no, ast.AsyncFunctionDef | ast.Await | ast.AsyncFor | ast.AsyncWith):
            raise CodigoRejeitado("async code is not allowed")
        if isinstance(no, ast.Name) and (no.id.startswith("_") or no.id in _NOMES_PROIBIDOS):
            raise CodigoRejeitado(f"name {no.id!r} is not allowed")
        if isinstance(no, ast.Attribute) and (
            no.attr.startswith("_") or no.attr in _ATRIBUTOS_PROIBIDOS
        ):
            raise CodigoRejeitado(f"attribute {no.attr!r} is not allowed")

    definidas = {no.name for no in arvore.body if isinstance(no, ast.FunctionDef)}
    if nome_funcao not in definidas:
        raise CodigoRejeitado(f"candidate must define a top-level function {nome_funcao!r}")


# Source of the child process. It is written to the temporary directory and run
# with ``python -I``. The exec calls below happen in that child, never here.
_RUNNER = r'''
import builtins
import json
import sys

PERMITIDOS = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
    "frozenset", "int", "isinstance", "len", "list", "map", "max", "min", "pow", "range",
    "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "ArithmeticError", "Exception", "IndexError", "KeyError", "TypeError", "ValueError",
    "ZeroDivisionError",
)
BLOQUEADOS = (
    "socket", "_socket", "ssl", "_ssl", "select", "selectors", "asyncio", "http", "urllib",
    "ftplib", "smtplib", "subprocess", "_posixsubprocess", "_winapi", "multiprocessing",
    "ctypes", "_ctypes",
)


class FormatoInvalido(Exception):
    pass


def limitar(segundos_cpu, bytes_memoria):
    try:
        import resource
    except ImportError:
        return
    for nome, valor in (("RLIMIT_CPU", segundos_cpu), ("RLIMIT_AS", bytes_memoria)):
        try:
            resource.setrlimit(getattr(resource, nome), (valor, valor))
        except (AttributeError, OSError, ValueError):
            pass


def ler(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return arquivo.read()


def rodar(entrada, codigo, harness):
    escopo_harness = {"FormatoInvalido": FormatoInvalido}
    exec(compile(harness, "harness.py", "exec"), escopo_harness)
    seguros = {nome: getattr(builtins, nome) for nome in PERMITIDOS}
    escopo = {"__builtins__": seguros, "__name__": "candidato"}
    exec(compile(codigo, "candidato.py", "exec"), escopo)
    funcao = escopo.get(entrada["nome_funcao"])
    if not callable(funcao):
        raise FormatoInvalido("candidate does not define " + entrada["nome_funcao"])
    executar = escopo_harness["executar"]
    return [executar(funcao, instancia) for instancia in entrada["instancias"]]


def main():
    entrada = json.loads(ler("entrada.json"))
    codigo = ler("candidato.py")
    harness = ler("harness.py")
    limitar(entrada["limite_cpu"], entrada["limite_memoria"])
    for nome in BLOQUEADOS:
        sys.modules[nome] = None
    try:
        texto = json.dumps({"ok": True, "saidas": rodar(entrada, codigo, harness)})
    except FormatoInvalido as erro:
        texto = json.dumps({"ok": False, "tipo": "formato_invalido", "erro": str(erro)[:500]})
    except Exception as erro:
        mensagem = (type(erro).__name__ + ": " + str(erro))[:500]
        texto = json.dumps({"ok": False, "tipo": "erro_execucao", "erro": mensagem})
    with open("saida.json", "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)


main()
'''


class Sandbox:
    """Runs one candidate per call in a fresh, isolated child interpreter."""

    def __init__(
        self,
        timeout: float = 5.0,
        limite_memoria_mb: int = 512,
        tamanho_maximo_saida: int = 5_000_000,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self.limite_memoria_mb = limite_memoria_mb
        self.tamanho_maximo_saida = tamanho_maximo_saida

    def executar(self, codigo: str, problema: Problema) -> ResultadoSandbox:
        """Run ``codigo`` against every instance of ``problema``.

        Never raises because of the candidate: every failure mode is reported
        through ``ResultadoSandbox.status``.
        """
        try:
            validar_codigo(codigo, problema.nome_funcao)
        except CodigoRejeitado as erro:
            return ResultadoSandbox(CODIGO_REJEITADO, erro=str(erro))

        instancias = problema.instancias()
        entrada = {
            "nome_funcao": problema.nome_funcao,
            "instancias": instancias,
            "limite_cpu": math.ceil(self.timeout) + 1,
            "limite_memoria": self.limite_memoria_mb * 1024 * 1024,
        }
        with tempfile.TemporaryDirectory(
            prefix="arquimedes-", ignore_cleanup_errors=True
        ) as nome_pasta:
            pasta = Path(nome_pasta)
            (pasta / "runner.py").write_text(_RUNNER, encoding="utf-8")
            (pasta / "candidato.py").write_text(codigo, encoding="utf-8")
            (pasta / "harness.py").write_text(problema.harness(), encoding="utf-8")
            (pasta / "entrada.json").write_text(json.dumps(entrada), encoding="utf-8")
            bruto = self._rodar_filho(pasta)

        if isinstance(bruto, ResultadoSandbox):
            return bruto
        return self._interpretar(bruto, instancias, problema)

    def _rodar_filho(self, pasta: Path) -> ResultadoSandbox | Any:
        ambiente = {}
        if os.name == "nt" and "SYSTEMROOT" in os.environ:
            # Windows refuses to start an interpreter without SYSTEMROOT.
            ambiente["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        try:
            processo = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-I", "runner.py"],
                cwd=pasta,
                env=ambiente,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ResultadoSandbox(TEMPO_ESGOTADO, erro=f"exceeded {self.timeout:g}s")
        except OSError as erro:
            return ResultadoSandbox(ERRO_EXECUCAO, erro=f"could not start sandbox: {erro}")

        saida = pasta / "saida.json"
        if not saida.is_file():
            return ResultadoSandbox(
                ERRO_EXECUCAO, erro=f"sandbox exited with code {processo.returncode}, no output"
            )
        if saida.stat().st_size > self.tamanho_maximo_saida:
            return ResultadoSandbox(FORMATO_INVALIDO, erro="output file is too large")
        try:
            return json.loads(saida.read_text(encoding="utf-8"))
        except (ValueError, OSError, RecursionError):
            return ResultadoSandbox(FORMATO_INVALIDO, erro="output file is not valid JSON")

    @staticmethod
    def _interpretar(bruto: Any, instancias: list[Any], problema: Problema) -> ResultadoSandbox:
        if not isinstance(bruto, dict) or not isinstance(bruto.get("ok"), bool):
            return ResultadoSandbox(FORMATO_INVALIDO, erro="malformed sandbox report")
        if not bruto["ok"]:
            status = FORMATO_INVALIDO if bruto.get("tipo") == FORMATO_INVALIDO else ERRO_EXECUCAO
            return ResultadoSandbox(status, erro=str(bruto.get("erro", ""))[:500])
        saidas = bruto.get("saidas")
        if not isinstance(saidas, list) or len(saidas) != len(instancias):
            return ResultadoSandbox(FORMATO_INVALIDO, erro="expected one output per instance")
        try:
            for instancia, saida in zip(instancias, saidas, strict=True):
                problema.validar_saida(instancia, saida)
        except SaidaInvalida as erro:
            return ResultadoSandbox(FORMATO_INVALIDO, erro=str(erro))
        return ResultadoSandbox(OK, saidas=saidas)
