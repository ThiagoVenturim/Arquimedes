"""Candidate generators. The laboratory only knows the ``Propositor`` protocol."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from arquimedes.problema import FIRST_FIT


@runtime_checkable
class Propositor(Protocol):
    """Anything that can suggest new candidate functions as source code."""

    def propor(self, melhor_atual: str) -> list[str]:
        """Return candidate sources, given the best source found so far.

        An empty list means "nothing else to try".
        """
        ...


BEST_FIT = '''\
def escolher_bin(item, livres):
    """Best-fit: the open bin left with the least room after the item."""
    melhor = -1
    menor_sobra = None
    for indice, livre in enumerate(livres):
        sobra = livre - item
        if sobra >= 0 and (menor_sobra is None or sobra < menor_sobra):
            melhor = indice
            menor_sobra = sobra
    return melhor
'''

WORST_FIT = '''\
def escolher_bin(item, livres):
    """Worst-fit: the open bin left with the most room after the item."""
    melhor = -1
    maior_sobra = -1
    for indice, livre in enumerate(livres):
        sobra = livre - item
        if sobra > maior_sobra:
            melhor = indice
            maior_sobra = sobra
    return melhor
'''

VARIANTES_BIN_PACKING: tuple[str, ...] = (FIRST_FIT, WORST_FIT, BEST_FIT)


class PropositorFake:
    """Deterministic proposer for tests and offline runs.

    Hands out a fixed list of variants, ``por_rodada`` at a time and always in
    the same order, then returns an empty list. It ignores ``melhor_atual``:
    there is no model behind it.
    """

    def __init__(
        self, variantes: Sequence[str] = VARIANTES_BIN_PACKING, por_rodada: int = 2
    ) -> None:
        if por_rodada < 1:
            raise ValueError("por_rodada must be at least 1")
        self._variantes = list(variantes)
        self._por_rodada = por_rodada
        self._posicao = 0

    def propor(self, melhor_atual: str) -> list[str]:
        lote = self._variantes[self._posicao : self._posicao + self._por_rodada]
        self._posicao += len(lote)
        return lote


_BLOCO_CODIGO = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.DOTALL)

_INSTRUCOES = """\
You are improving a heuristic. Below is the best version found so far.
Write {quantidade} different improved versions of the same function.
Keep the function name and signature. Use only plain Python: no imports,
no file or network access. Put each version in its own ```python block.

{codigo}
"""


class PropositorLLM:
    """Adapter that turns any text generator into a ``Propositor``.

    ``gerar`` is a callable ``prompt -> text`` supplied by the caller. This
    class does not talk to any provider and ships no network code: wiring a
    real model (through nexcoder-core or a provider SDK) means passing the
    right callable here. Everything it returns is untrusted text and still goes
    through the sandbox like any other candidate.
    """

    def __init__(self, gerar: Callable[[str], str], quantidade: int = 3) -> None:
        if quantidade < 1:
            raise ValueError("quantidade must be at least 1")
        self._gerar = gerar
        self._quantidade = quantidade

    def propor(self, melhor_atual: str) -> list[str]:
        prompt = _INSTRUCOES.format(quantidade=self._quantidade, codigo=melhor_atual)
        resposta = self._gerar(prompt)
        if not isinstance(resposta, str):
            return []
        return extrair_blocos(resposta)[: self._quantidade]


def extrair_blocos(texto: str) -> list[str]:
    """Return the contents of every fenced Python block found in ``texto``."""
    return [bloco.strip() + "\n" for bloco in _BLOCO_CODIGO.findall(texto) if bloco.strip()]
