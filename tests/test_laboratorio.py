from __future__ import annotations

import pytest

from arquimedes.laboratorio import ErroLaboratorio, Laboratorio
from arquimedes.problema import FIRST_FIT, BinPackingOnline
from arquimedes.propositor import BEST_FIT, WORST_FIT, PropositorFake
from arquimedes.sandbox import CODIGO_REJEITADO, FORMATO_INVALIDO, OK, TEMPO_ESGOTADO, Sandbox


def test_acha_best_fit_melhor_que_first_fit_e_registra_o_ganho():
    laboratorio = Laboratorio(BinPackingOnline(), PropositorFake())
    relatorio = laboratorio.rodar(iteracoes=5)

    assert relatorio.baseline.codigo == FIRST_FIT
    assert relatorio.baseline.pontuacao == 221.0
    assert relatorio.melhor.codigo == BEST_FIT
    assert relatorio.melhor.pontuacao == 218.0
    assert relatorio.melhor.pontuacao < relatorio.baseline.pontuacao
    assert relatorio.ganho == 3.0
    assert relatorio.ganho_percentual == pytest.approx(100 * 3 / 221)
    assert relatorio.melhor.iteracao == 2


def test_banco_fica_ordenado_e_sem_duplicatas():
    relatorio = Laboratorio(BinPackingOnline(), PropositorFake()).rodar(iteracoes=5)
    assert [registro.codigo for registro in relatorio.banco] == [BEST_FIT, FIRST_FIT, WORST_FIT]
    pontuacoes = [registro.pontuacao for registro in relatorio.banco]
    assert pontuacoes == sorted(pontuacoes)


def test_banco_respeita_o_tamanho_maximo():
    laboratorio = Laboratorio(BinPackingOnline(), PropositorFake(), tamanho_banco=1)
    relatorio = laboratorio.rodar(iteracoes=5)
    assert [registro.codigo for registro in relatorio.banco] == [BEST_FIT]


def test_duas_execucoes_dao_o_mesmo_resultado():
    primeiro = Laboratorio(BinPackingOnline(), PropositorFake()).rodar(iteracoes=5)
    segundo = Laboratorio(BinPackingOnline(), PropositorFake()).rodar(iteracoes=5)
    assert primeiro.melhor == segundo.melhor
    assert primeiro.tentativas == segundo.tentativas


def test_para_cedo_sem_melhora():
    relatorio = Laboratorio(BinPackingOnline(), PropositorFake()).rodar(iteracoes=50, paciencia=2)
    assert relatorio.iteracoes_executadas == 4


def test_zero_iteracoes_devolve_o_baseline():
    relatorio = Laboratorio(BinPackingOnline(), PropositorFake()).rodar(iteracoes=0)
    assert relatorio.melhor == relatorio.baseline
    assert relatorio.ganho == 0.0
    assert relatorio.tentativas == []


def test_candidatos_ruins_sao_descartados_sem_parar_a_busca(problema_pequeno):
    ruins = [
        "import os\ndef escolher_bin(item, livres):\n    return -1\n",
        "def escolher_bin(item, livres):\n    while True:\n        pass\n",
        "def escolher_bin(item, livres):\n    return 'zero'\n",
    ]
    propositor = PropositorFake([*ruins, BEST_FIT], por_rodada=4)
    laboratorio = Laboratorio(problema_pequeno, propositor, Sandbox(timeout=1.0))
    relatorio = laboratorio.rodar(iteracoes=1)

    assert [tentativa.status for tentativa in relatorio.tentativas] == [
        CODIGO_REJEITADO,
        TEMPO_ESGOTADO,
        FORMATO_INVALIDO,
        OK,
    ]
    assert relatorio.baseline.pontuacao == 3.0
    assert relatorio.melhor.codigo == BEST_FIT
    assert relatorio.melhor.pontuacao == 2.0
    assert all(registro.codigo not in ruins for registro in relatorio.banco)


def test_candidato_repetido_nao_e_executado_de_novo(problema_pequeno, monkeypatch):
    sandbox = Sandbox()
    execucoes = []
    original = sandbox.executar

    def contando(codigo, problema):
        execucoes.append(codigo)
        return original(codigo, problema)

    monkeypatch.setattr(sandbox, "executar", contando)
    propositor = PropositorFake([BEST_FIT, BEST_FIT, FIRST_FIT], por_rodada=3)
    Laboratorio(problema_pequeno, propositor, sandbox).rodar(iteracoes=1)
    assert execucoes == [FIRST_FIT, BEST_FIT]


def test_baseline_quebrado_interrompe_com_erro_claro(problema_pequeno, monkeypatch):
    monkeypatch.setattr(problema_pequeno, "baseline", lambda: "import os\n")
    with pytest.raises(ErroLaboratorio, match="baseline"):
        Laboratorio(problema_pequeno, PropositorFake()).rodar(iteracoes=1)


@pytest.mark.parametrize("argumentos", [{"iteracoes": -1}, {"paciencia": 0}])
def test_parametros_invalidos(problema_pequeno, argumentos):
    with pytest.raises(ValueError):
        Laboratorio(problema_pequeno, PropositorFake()).rodar(**argumentos)
