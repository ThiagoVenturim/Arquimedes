from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from arquimedes.propositor import BEST_FIT
from arquimedes.sandbox import (
    CODIGO_REJEITADO,
    ERRO_EXECUCAO,
    FORMATO_INVALIDO,
    TEMPO_ESGOTADO,
    CodigoRejeitado,
    Sandbox,
    validar_codigo,
)

LACO_INFINITO = """\
def escolher_bin(item, livres):
    while True:
        pass
"""

RETORNA_TEXTO = """\
def escolher_bin(item, livres):
    return "primeiro"
"""

BIN_CHEIO = """\
def escolher_bin(item, livres):
    return 0 if livres else -1
"""

LEVANTA_ERRO = """\
def escolher_bin(item, livres):
    return 1 // 0
"""


def test_executa_candidato_valido(problema_pequeno):
    resultado = Sandbox().executar(BEST_FIT, problema_pequeno)
    assert resultado.ok
    assert resultado.saidas == [[0, 1, 1, 0]]


def test_rejeita_candidato_que_estoura_o_tempo(problema_pequeno):
    inicio = time.monotonic()
    resultado = Sandbox(timeout=1.0).executar(LACO_INFINITO, problema_pequeno)
    assert resultado.status == TEMPO_ESGOTADO
    assert resultado.saidas is None
    assert time.monotonic() - inicio < 10


def test_rejeita_candidato_com_formato_errado(problema_pequeno):
    resultado = Sandbox().executar(RETORNA_TEXTO, problema_pequeno)
    assert resultado.status == FORMATO_INVALIDO
    assert resultado.saidas is None


def test_rejeita_escolha_de_bin_sem_espaco(problema_pequeno):
    resultado = Sandbox().executar(BIN_CHEIO, problema_pequeno)
    assert resultado.status == FORMATO_INVALIDO


def test_erro_do_candidato_nao_derruba_o_processo_principal(problema_pequeno):
    resultado = Sandbox().executar(LEVANTA_ERRO, problema_pequeno)
    assert resultado.status == ERRO_EXECUCAO
    assert "ZeroDivisionError" in resultado.erro


def test_relatorio_forjado_pelo_filho_e_revalidado(problema_pequeno):
    """Even an "ok" report is replayed by the verifier in the main process."""
    forjado = {"ok": True, "saidas": [[0, 0, 0, 0]]}
    instancias = problema_pequeno.instancias()
    resultado = Sandbox._interpretar(forjado, instancias, problema_pequeno)
    assert resultado.status == FORMATO_INVALIDO


@pytest.mark.parametrize("bruto", [None, [], {"ok": "sim"}, {"ok": True}, {"ok": True, "saidas": 3}])
def test_relatorio_malformado(problema_pequeno, bruto):
    resultado = Sandbox._interpretar(bruto, problema_pequeno.instancias(), problema_pequeno)
    assert resultado.status == FORMATO_INVALIDO


@pytest.mark.parametrize(
    "codigo",
    [
        "import os\ndef escolher_bin(item, livres):\n    return -1\n",
        "from socket import socket\ndef escolher_bin(item, livres):\n    return -1\n",
        "def escolher_bin(item, livres):\n    return __import__('os').getpid()\n",
        "def escolher_bin(item, livres):\n    open('x', 'w')\n    return -1\n",
        "def escolher_bin(item, livres):\n    return eval('1')\n",
        "def escolher_bin(item, livres):\n    return exec('x = 1')\n",
        "def escolher_bin(item, livres):\n    return ().__class__.__mro__\n",
        "def escolher_bin(item, livres):\n    return (i for i in livres).gi_frame.f_back\n",
        "def escolher_bin(item, livres):\n    return getattr(livres, 'append')\n",
        "class A:\n    pass\ndef escolher_bin(item, livres):\n    return -1\n",
        "def outra_funcao(item, livres):\n    return -1\n",
        "def escolher_bin(item, livres)\n    return -1\n",
        "escolher_bin = lambda item, livres: -1\n",
        "",
    ],
)
def test_validacao_estatica_rejeita(codigo):
    with pytest.raises(CodigoRejeitado):
        validar_codigo(codigo, "escolher_bin")


def test_validacao_estatica_rejeita_codigo_enorme():
    codigo = "def escolher_bin(item, livres):\n    return -1\n" + "# x\n" * 10_000
    with pytest.raises(CodigoRejeitado):
        validar_codigo(codigo, "escolher_bin")


def test_validacao_estatica_rejeita_o_que_nao_e_texto():
    with pytest.raises(CodigoRejeitado):
        validar_codigo(None, "escolher_bin")


def test_codigo_rejeitado_nunca_inicia_um_processo(problema_pequeno, monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("rejected code must not reach the child process")

    monkeypatch.setattr("arquimedes.sandbox.subprocess.run", proibido)
    resultado = Sandbox().executar("import os\n", problema_pequeno)
    assert resultado.status == CODIGO_REJEITADO


def test_codigo_de_modulo_nao_roda_no_processo_principal(problema_pequeno):
    """Top-level statements run in the child only: the parent's state is untouched."""
    codigo = "livres_globais = [1, 2, 3]\n" + BEST_FIT
    antes = set(globals())
    resultado = Sandbox().executar(codigo, problema_pequeno)
    assert resultado.ok
    assert set(globals()) == antes


def test_filho_roda_isolado_com_ambiente_vazio(problema_pequeno, monkeypatch):
    chamadas = []
    original = __import__("subprocess").run

    def espiao(argv, **kwargs):
        chamadas.append((argv, kwargs))
        return original(argv, **kwargs)

    monkeypatch.setenv("SEGREDO_DE_TESTE", "nao-pode-vazar")
    monkeypatch.setattr("arquimedes.sandbox.subprocess.run", espiao)
    assert Sandbox().executar(BEST_FIT, problema_pequeno).ok

    (argv, kwargs), = chamadas
    assert argv[1] == "-I"
    assert "SEGREDO_DE_TESTE" not in kwargs["env"]
    assert set(kwargs["env"]) <= {"SYSTEMROOT"}
    assert Path(kwargs["cwd"]).name.startswith("arquimedes-")
    assert "shell" not in kwargs


def test_pasta_temporaria_e_removida(problema_pequeno):
    def pastas():
        return {nome for nome in os.listdir(tempfile.gettempdir()) if nome.startswith("arquimedes-")}

    antes = pastas()
    Sandbox().executar(BEST_FIT, problema_pequeno)
    Sandbox(timeout=1.0).executar(LACO_INFINITO, problema_pequeno)
    assert pastas() <= antes


def test_timeout_precisa_ser_positivo():
    with pytest.raises(ValueError):
        Sandbox(timeout=0)
