from __future__ import annotations

import pytest

from arquimedes.problema import FIRST_FIT
from arquimedes.propositor import (
    BEST_FIT,
    WORST_FIT,
    Propositor,
    PropositorFake,
    PropositorLLM,
    extrair_blocos,
)


def test_fake_entrega_as_variantes_em_ordem_e_depois_esgota():
    propositor = PropositorFake()
    assert propositor.propor(FIRST_FIT) == [FIRST_FIT, WORST_FIT]
    assert propositor.propor(FIRST_FIT) == [BEST_FIT]
    assert propositor.propor(BEST_FIT) == []
    assert propositor.propor(BEST_FIT) == []


def test_fake_e_deterministico():
    a, b = PropositorFake(), PropositorFake()
    assert [a.propor("x") for _ in range(3)] == [b.propor("y") for _ in range(3)]


def test_fake_exige_lote_positivo():
    with pytest.raises(ValueError):
        PropositorFake(por_rodada=0)


def test_implementacoes_cumprem_o_protocolo():
    assert isinstance(PropositorFake(), Propositor)
    assert isinstance(PropositorLLM(lambda prompt: ""), Propositor)


def test_llm_usa_o_gerador_injetado_e_extrai_os_blocos():
    prompts = []

    def gerador_falso(prompt: str) -> str:
        prompts.append(prompt)
        return f"Here you go.\n```python\n{BEST_FIT}```\nand\n```py\n{WORST_FIT}```\n"

    propositor = PropositorLLM(gerador_falso, quantidade=2)
    assert propositor.propor(FIRST_FIT) == [BEST_FIT, WORST_FIT]
    assert FIRST_FIT in prompts[0]


def test_llm_limita_a_quantidade_e_tolera_resposta_sem_codigo():
    tres = "```python\na = 1\n```\n```python\nb = 2\n```\n```python\nc = 3\n```"
    assert PropositorLLM(lambda prompt: tres, quantidade=2).propor("x") == ["a = 1\n", "b = 2\n"]
    assert PropositorLLM(lambda prompt: "sorry, no idea").propor("x") == []
    assert PropositorLLM(lambda prompt: None).propor("x") == []


def test_extrair_blocos_ignora_blocos_vazios():
    assert extrair_blocos("```python\n\n```\n```\nx = 1\n```") == ["x = 1\n"]
