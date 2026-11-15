"""Command line entry point: ``arquimedes rodar``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from arquimedes import __version__
from arquimedes.laboratorio import ErroLaboratorio, Laboratorio, Relatorio
from arquimedes.problema import PROBLEMAS, criar_problema
from arquimedes.propositor import PropositorFake
from arquimedes.sandbox import Sandbox


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arquimedes",
        description="Laboratorio de busca de heuristicas: propor, testar em sandbox, medir.",
    )
    parser.add_argument("--version", action="version", version=f"arquimedes {__version__}")
    comandos = parser.add_subparsers(dest="comando", required=True)

    rodar = comandos.add_parser("rodar", help="roda o ciclo de busca com o propositor fake")
    rodar.add_argument("--problema", choices=sorted(PROBLEMAS), default="bin_packing")
    rodar.add_argument("--iteracoes", type=int, default=5, help="maximo de rodadas (padrao: 5)")
    rodar.add_argument(
        "--paciencia", type=int, default=2, help="rodadas sem melhora antes de parar (padrao: 2)"
    )
    rodar.add_argument(
        "--timeout", type=float, default=5.0, help="segundos por candidato no sandbox (padrao: 5)"
    )
    return parser


def _formatar(relatorio: Relatorio, nome_problema: str) -> str:
    linhas = [
        f"Problema: {nome_problema} (pontuacao = custo, menor e melhor)",
        f"Iteracoes executadas: {relatorio.iteracoes_executadas}",
        f"Baseline: {relatorio.baseline.pontuacao:g}",
        "Tentativas:",
    ]
    for tentativa in relatorio.tentativas:
        pontuacao = "-" if tentativa.pontuacao is None else f"{tentativa.pontuacao:g}"
        detalhe = f" ({tentativa.erro})" if tentativa.erro else ""
        linhas.append(
            f"  iteracao {tentativa.iteracao}: {tentativa.status}, pontuacao {pontuacao}{detalhe}"
        )
    linhas.append(
        f"Melhor: {relatorio.melhor.pontuacao:g} (achado na iteracao {relatorio.melhor.iteracao})"
    )
    linhas.append(f"Ganho sobre o baseline: {relatorio.ganho:g} ({relatorio.ganho_percentual:.2f}%)")
    linhas.append("Codigo do melhor:")
    linhas.append(relatorio.melhor.codigo.rstrip())
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    if args.iteracoes < 0 or args.paciencia < 1 or args.timeout <= 0:
        print("erro: --iteracoes >= 0, --paciencia >= 1 e --timeout > 0", file=sys.stderr)
        return 2
    problema = criar_problema(args.problema)
    laboratorio = Laboratorio(problema, PropositorFake(), Sandbox(timeout=args.timeout))
    try:
        relatorio = laboratorio.rodar(iteracoes=args.iteracoes, paciencia=args.paciencia)
    except ErroLaboratorio as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    print(_formatar(relatorio, problema.nome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
