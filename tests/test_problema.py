from __future__ import annotations

import pytest

from arquimedes.problema import BinPackingOnline, Problema, SaidaInvalida, criar_problema
from arquimedes.sandbox import Sandbox


def test_instancias_sao_deterministicas():
    primeira = BinPackingOnline().instancias()
    segunda = BinPackingOnline().instancias()
    assert primeira == segunda
    assert len(primeira) == 5
    assert all(len(instancia["itens"]) == 120 for instancia in primeira)
    assert all(10 <= item <= 60 for instancia in primeira for item in instancia["itens"])


def test_baseline_e_reprodutivel():
    problema = BinPackingOnline()
    pontuacoes = []
    for _ in range(2):
        resultado = Sandbox().executar(problema.baseline(), problema)
        assert resultado.ok, resultado.erro
        pontuacoes.append(problema.avaliar(resultado.saidas))
    assert pontuacoes == [221.0, 221.0]


def test_baseline_no_caso_conferido_a_mao(problema_pequeno):
    resultado = Sandbox().executar(problema_pequeno.baseline(), problema_pequeno)
    assert resultado.saidas == [[0, 1, 0, 2]]
    assert problema_pequeno.avaliar(resultado.saidas) == 3.0


def test_bin_packing_cumpre_o_protocolo():
    assert isinstance(criar_problema("bin_packing"), Problema)


def test_problema_desconhecido():
    with pytest.raises(ValueError, match="unknown problem"):
        criar_problema("caixeiro_viajante")


@pytest.mark.parametrize(
    "saida",
    [
        "0102",  # not a list
        [0, 1, 0],  # one assignment missing
        [0, 0, 1, 2],  # bin 0 would hold 50 + 60
        [0, 2, 1, 1],  # opens bin 2 before bin 1
        [0, 1, 1.0, 0],  # float index
        [0, 1, True, 0],  # bool is not an accepted index
        [0, -1, 1, 0],  # negative index
    ],
)
def test_verificador_rejeita_saida_invalida(problema_pequeno, saida):
    with pytest.raises(SaidaInvalida):
        problema_pequeno.avaliar([saida])


def test_verificador_exige_uma_saida_por_instancia(problema_pequeno):
    with pytest.raises(SaidaInvalida):
        problema_pequeno.avaliar([])


def test_verificador_aceita_empacotamento_valido(problema_pequeno):
    assert problema_pequeno.avaliar([[0, 1, 1, 0]]) == 2.0


def test_avaliar_aceita_codigo_candidato_direto(problema_pequeno):
    assert problema_pequeno.avaliar(problema_pequeno.baseline()) == 3.0
    with pytest.raises(SaidaInvalida):
        problema_pequeno.avaliar("import os\n")
