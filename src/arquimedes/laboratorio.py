"""The search loop: propose, run in the sandbox, measure, keep the best."""

from __future__ import annotations

from dataclasses import dataclass, field

from arquimedes.problema import Problema, SaidaInvalida
from arquimedes.propositor import Propositor
from arquimedes.sandbox import FORMATO_INVALIDO, OK, Sandbox


class ErroLaboratorio(RuntimeError):
    """The laboratory cannot run, for example because the baseline itself fails."""


@dataclass(frozen=True)
class Registro:
    """A scored candidate kept in the bank."""

    pontuacao: float
    codigo: str
    iteracao: int


@dataclass(frozen=True)
class Tentativa:
    """One candidate evaluation, successful or not."""

    iteracao: int
    status: str
    pontuacao: float | None
    codigo: str
    erro: str = ""


@dataclass
class Relatorio:
    """What a run found. Scores are costs: lower is better."""

    baseline: Registro
    melhor: Registro
    banco: list[Registro]
    tentativas: list[Tentativa] = field(default_factory=list)
    iteracoes_executadas: int = 0

    @property
    def ganho(self) -> float:
        """Absolute improvement over the baseline (positive means better)."""
        return self.baseline.pontuacao - self.melhor.pontuacao

    @property
    def ganho_percentual(self) -> float:
        if self.baseline.pontuacao == 0:
            return 0.0
        return 100.0 * self.ganho / abs(self.baseline.pontuacao)


class Laboratorio:
    """Runs the propose/test/measure/keep cycle for one problem."""

    def __init__(
        self,
        problema: Problema,
        propositor: Propositor,
        sandbox: Sandbox | None = None,
        tamanho_banco: int = 5,
    ) -> None:
        if tamanho_banco < 1:
            raise ValueError("tamanho_banco must be at least 1")
        self.problema = problema
        self.propositor = propositor
        self.sandbox = sandbox or Sandbox()
        self.tamanho_banco = tamanho_banco
        self._vistos: dict[str, Tentativa] = {}

    def rodar(self, iteracoes: int = 5, paciencia: int = 2) -> Relatorio:
        """Search for at most ``iteracoes`` rounds.

        Stops early after ``paciencia`` consecutive rounds without a new best.
        """
        if iteracoes < 0:
            raise ValueError("iteracoes must not be negative")
        if paciencia < 1:
            raise ValueError("paciencia must be at least 1")

        inicial = self._medir(self.problema.baseline(), iteracao=0)
        if inicial.pontuacao is None:
            raise ErroLaboratorio(f"baseline failed in the sandbox: {inicial.status} {inicial.erro}")
        baseline = Registro(inicial.pontuacao, inicial.codigo, 0)
        relatorio = Relatorio(baseline=baseline, melhor=baseline, banco=[baseline])

        sem_melhora = 0
        for iteracao in range(1, iteracoes + 1):
            relatorio.iteracoes_executadas = iteracao
            melhorou = False
            for codigo in self.propositor.propor(relatorio.melhor.codigo):
                tentativa = self._medir(codigo, iteracao)
                relatorio.tentativas.append(tentativa)
                if tentativa.pontuacao is None:
                    continue
                registro = Registro(tentativa.pontuacao, tentativa.codigo, iteracao)
                self._guardar(relatorio, registro)
                if registro.pontuacao < relatorio.melhor.pontuacao:
                    relatorio.melhor = registro
                    melhorou = True
            sem_melhora = 0 if melhorou else sem_melhora + 1
            if sem_melhora >= paciencia:
                break
        return relatorio

    def _medir(self, codigo: str, iteracao: int) -> Tentativa:
        """Run one candidate in the sandbox and score it. Repeats are served from cache."""
        if isinstance(codigo, str) and codigo in self._vistos:
            anterior = self._vistos[codigo]
            return Tentativa(iteracao, anterior.status, anterior.pontuacao, codigo, anterior.erro)

        resultado = self.sandbox.executar(codigo, self.problema)
        if resultado.status == OK and resultado.saidas is not None:
            try:
                pontuacao = float(self.problema.avaliar(resultado.saidas))
                tentativa = Tentativa(iteracao, OK, pontuacao, codigo)
            except SaidaInvalida as erro:
                tentativa = Tentativa(iteracao, FORMATO_INVALIDO, None, codigo, str(erro))
        else:
            tentativa = Tentativa(iteracao, resultado.status, None, str(codigo), resultado.erro)
        if isinstance(codigo, str):
            self._vistos[codigo] = tentativa
        return tentativa

    def _guardar(self, relatorio: Relatorio, registro: Registro) -> None:
        """Keep the bank sorted by score, without duplicates, capped at ``tamanho_banco``."""
        if any(existente.codigo == registro.codigo for existente in relatorio.banco):
            return
        relatorio.banco.append(registro)
        relatorio.banco.sort(key=lambda item: (item.pontuacao, item.iteracao))
        del relatorio.banco[self.tamanho_banco :]
