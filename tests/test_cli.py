from __future__ import annotations

import pytest

from arquimedes.cli import main


def test_rodar_imprime_o_melhor_e_o_ganho(capsys):
    assert main(["rodar", "--problema", "bin_packing", "--iteracoes", "5"]) == 0
    saida = capsys.readouterr().out
    assert "Baseline: 221" in saida
    assert "Melhor: 218" in saida
    assert "Ganho sobre o baseline: 3 (1.36%)" in saida
    assert "Best-fit" in saida


def test_rodar_recusa_parametros_invalidos(capsys):
    assert main(["rodar", "--iteracoes", "-1"]) == 2
    assert "erro" in capsys.readouterr().err


def test_problema_desconhecido_e_recusado_pelo_parser():
    with pytest.raises(SystemExit):
        main(["rodar", "--problema", "nao_existe"])
