# Arquimedes

A Python laboratory inspired by FunSearch: propose candidate functions, run them in an
isolated sandbox, score them with an objective verifier, and keep the best ones.

Status: early MVP.

## What it does and what it does not

Searching the space of small heuristics with a model and a fast, deterministic verifier
works today on narrow problems where any candidate answer can be checked cheaply. That is
the pattern behind AlphaTensor (Fawzi et al., *Nature* 2022, matrix multiplication),
AlphaDev (Mankowitz et al., *Nature* 2023, short sorting routines), and FunSearch
(Romera-Paredes et al., *Nature* 2024, evolving Python heuristics for cap sets and online
bin packing).

Arquimedes implements that loop in plain Python, starting with online bin packing:

1. Start from a reference heuristic (`first-fit`, 221 bins on the built-in benchmark).
2. Ask a `Propositor` for candidate replacements of the decision function
   `escolher_bin(item, livres) -> int`.
3. Validate the AST and execute each candidate in a separate `python -I` process with no
   network, a wall-clock timeout, restricted builtins, and file-only I/O inside a temporary
   directory.
4. Replay and verify the returned bin assignments in the main process, count the bins used,
   and keep the lowest-cost candidates in a ranked bank.

What this MVP does **not** do: invent a new neural architecture to replace the Transformer
or discover general algorithms without an explicit verifier. Open-ended architecture search
is a long-term research direction, not something this package claims to deliver.

## Security model

Every candidate is untrusted generated code:

- The main process never calls `eval` or `exec` on candidate text. It only parses the
  source with `ast.parse` and rejects imports, dunder access, classes, async constructs,
  and dangerous builtins before starting a child process.
- Execution happens in a fresh `python -I` subprocess with an empty environment, a private
  temporary working directory, a strict timeout, blocked network and process modules, and
  an allowlist of safe builtins.
- The main process trusts nothing reported by the child beyond raw JSON assignments, which
  the problem verifier replays from scratch.

Even with these layers, a child Python interpreter still runs under the current operating
system user. When connecting a real LLM, run Arquimedes inside an unprivileged container
or VM with network disabled.

## Install and run

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
git config core.hooksPath .githooks
```

Run the search loop offline with the deterministic fake proposer:

```bash
arquimedes rodar --problema bin_packing --iteracoes 5
```

Output:

```text
Problema: bin_packing (pontuacao = custo, menor e melhor)
Iteracoes executadas: 4
Baseline: 221
Tentativas:
  iteracao 1: ok, pontuacao 221
  iteracao 1: ok, pontuacao 232
  iteracao 2: ok, pontuacao 218
Melhor: 218 (achado na iteracao 2)
Ganho sobre o baseline: 3 (1.36%)
```

## Plugging an LLM proposer

Tests and the default CLI use `PropositorFake`, which requires no network or API keys. To
connect a model (for example through `nexcoder-core` or a local server), pass any callable
`prompt -> str` to `PropositorLLM`:

```python
from arquimedes.laboratorio import Laboratorio
from arquimedes.problema import BinPackingOnline
from arquimedes.propositor import PropositorLLM

propositor = PropositorLLM(gerar=minha_funcao_llm, quantidade=3)
relatorio = Laboratorio(BinPackingOnline(), propositor).rodar(iteracoes=10)
```

## Verification

```bash
ruff check .
python -m pytest
python scripts/check_no_emoji.py
```

See `docs/ARCHITECTURE.md` for module boundaries and sandbox details. Portuguese version:
`README.pt-BR.md`. License: MIT.
