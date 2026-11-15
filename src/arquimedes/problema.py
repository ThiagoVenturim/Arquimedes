"""Problems the laboratory can optimise, each with an objective verifier.

A problem never calls candidate code itself. The candidate runs inside the
sandbox (a separate process); the problem only supplies the instances, the
small trusted driver that feeds them to the candidate inside that process, and
the verifier that checks and scores what came back.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class SaidaInvalida(ValueError):
    """The output produced by a candidate breaks the problem's rules."""


@runtime_checkable
class Problema(Protocol):
    """Contract between a concrete problem and the laboratory.

    Scores are always "lower is better" (a cost). A problem that naturally
    maximises something should return the negated value.
    """

    nome: str
    nome_funcao: str

    def instancias(self) -> list[Any]:
        """Return the benchmark cases. Must be deterministic and JSON-serialisable."""
        ...

    def harness(self) -> str:
        """Return trusted Python source defining ``executar(funcao, instancia)``.

        It runs inside the sandbox process, next to the candidate, and returns
        the JSON-serialisable output for one instance. It may raise
        ``FormatoInvalido`` (injected by the sandbox runner) when the candidate
        returns something unusable.
        """
        ...

    def validar_saida(self, instancia: Any, saida: Any) -> None:
        """Raise ``SaidaInvalida`` unless ``saida`` is a legal answer for ``instancia``."""
        ...

    def avaliar(self, saidas: list[Any] | str) -> float:
        """Validate the outputs (or run a candidate source in the sandbox) and return the score. Lower is better."""
        ...

    def baseline(self) -> str:
        """Return the source code of the reference heuristic."""
        ...


FIRST_FIT = '''\
def escolher_bin(item, livres):
    """First-fit: the first open bin with enough room."""
    for indice, livre in enumerate(livres):
        if livre >= item:
            return indice
    return -1
'''

_HARNESS_BIN_PACKING = '''\
def executar(funcao, instancia):
    capacidade = instancia["capacidade"]
    livres = []
    atribuicoes = []
    for item in instancia["itens"]:
        escolha = funcao(item, list(livres))
        if type(escolha) is not int:
            raise FormatoInvalido(
                "escolher_bin must return an int, got " + type(escolha).__name__
            )
        if escolha == -1:
            livres.append(capacidade - item)
            atribuicoes.append(len(livres) - 1)
        elif 0 <= escolha < len(livres) and livres[escolha] >= item:
            livres[escolha] -= item
            atribuicoes.append(escolha)
        else:
            raise FormatoInvalido("escolher_bin chose a bin that cannot hold the item")
    return atribuicoes
'''


def _gerar_itens(semente: int, quantidade: int, minimo: int, maximo: int) -> list[int]:
    """Generate item sizes with a fixed LCG so the benchmark never changes.

    The standard ``random`` module is avoided on purpose: this sequence must be
    identical on every Python version and platform.
    """
    estado = semente & 0x7FFFFFFF
    itens = []
    for _ in range(quantidade):
        estado = (1103515245 * estado + 12345) % 2147483648
        itens.append(minimo + (estado >> 8) % (maximo - minimo + 1))
    return itens


class BinPackingOnline:
    """Online bin packing: items arrive one at a time and are placed for good.

    The candidate is a function ``escolher_bin(item, livres) -> int`` where
    ``livres`` is the free space of every open bin. It returns the index of the
    bin that receives the item, or ``-1`` to open a new bin. The score is the
    total number of bins used over all instances (lower is better).
    """

    nome = "bin_packing"
    nome_funcao = "escolher_bin"

    def __init__(
        self,
        capacidade: int = 100,
        itens_por_instancia: int = 120,
        sementes: tuple[int, ...] = (11, 23, 37, 41, 59),
        tamanho_minimo: int = 10,
        tamanho_maximo: int = 60,
    ) -> None:
        if not 0 < tamanho_minimo <= tamanho_maximo <= capacidade:
            raise ValueError("item sizes must satisfy 0 < minimo <= maximo <= capacidade")
        self.capacidade = capacidade
        self.itens_por_instancia = itens_por_instancia
        self.sementes = tuple(sementes)
        self.tamanho_minimo = tamanho_minimo
        self.tamanho_maximo = tamanho_maximo

    def instancias(self) -> list[dict[str, Any]]:
        return [
            {
                "capacidade": self.capacidade,
                "itens": _gerar_itens(
                    semente, self.itens_por_instancia, self.tamanho_minimo, self.tamanho_maximo
                ),
            }
            for semente in self.sementes
        ]

    def harness(self) -> str:
        return _HARNESS_BIN_PACKING

    def baseline(self) -> str:
        return FIRST_FIT

    def validar_saida(self, instancia: dict[str, Any], saida: Any) -> None:
        self._contar_bins(instancia, saida)

    def avaliar(self, saidas: list[Any] | str) -> float:
        if isinstance(saidas, str):
            from arquimedes.sandbox import Sandbox

            resultado = Sandbox().executar(saidas, self)
            if not resultado.ok or resultado.saidas is None:
                raise SaidaInvalida(
                    f"candidate failed in sandbox ({resultado.status}): {resultado.erro}"
                )
            saidas = resultado.saidas
        instancias = self.instancias()
        if not isinstance(saidas, list) or len(saidas) != len(instancias):
            raise SaidaInvalida(f"expected {len(instancias)} outputs, one per instance")
        total = 0
        for instancia, saida in zip(instancias, saidas, strict=True):
            total += self._contar_bins(instancia, saida)
        return float(total)

    @staticmethod
    def _contar_bins(instancia: dict[str, Any], saida: Any) -> int:
        """Replay the assignment and return how many bins it uses.

        This is the objective verifier. It runs in the main process and trusts
        nothing reported by the sandbox beyond the raw assignment list.
        """
        itens = instancia["itens"]
        capacidade = instancia["capacidade"]
        if not isinstance(saida, list):
            raise SaidaInvalida("output must be a list with one bin index per item")
        if len(saida) != len(itens):
            raise SaidaInvalida(f"expected {len(itens)} assignments, got {len(saida)}")
        cargas: list[int] = []
        for item, indice in zip(itens, saida, strict=True):
            if type(indice) is not int:
                raise SaidaInvalida("bin indexes must be integers")
            if indice == len(cargas):
                cargas.append(0)
            elif not 0 <= indice < len(cargas):
                raise SaidaInvalida(f"bin index {indice} is out of sequence")
            cargas[indice] += item
            if cargas[indice] > capacidade:
                raise SaidaInvalida(f"bin {indice} exceeds capacity {capacidade}")
        return len(cargas)


PROBLEMAS: dict[str, type] = {BinPackingOnline.nome: BinPackingOnline}


def criar_problema(nome: str) -> Problema:
    """Build a registered problem by name."""
    try:
        return PROBLEMAS[nome]()
    except KeyError:
        conhecidos = ", ".join(sorted(PROBLEMAS))
        raise ValueError(f"unknown problem {nome!r}; available: {conhecidos}") from None
