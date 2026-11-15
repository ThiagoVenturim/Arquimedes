# Arquimedes architecture

Arquimedes is a small FunSearch-style search engine for heuristics. It separates problem
definition, candidate generation, untrusted execution, and the search loop so that every
part can be tested offline and swapped independently.

## Modules (`src/arquimedes/`)

- `problema.py`: defines the `Problema` protocol (`instancias()`, `harness()`,
  `validar_saida()`, `avaliar()`, `baseline()`) and the concrete `BinPackingOnline`
  benchmark. Scores are always costs (lower is better). Instance generation uses a fixed
  linear congruential generator so the benchmark is identical across Python versions and
  operating systems.
- `propositor.py`: defines the `Propositor` protocol (`propor(melhor_atual) -> list[str]`).
  Includes `PropositorFake` (deterministic, hands out `first-fit`, `worst-fit`, and
  `best-fit` for offline tests and CLI runs) and `PropositorLLM`, which wraps any
  `Callable[[str], str]` (such as a `nexcoder-core` adapter) and extracts fenced Python
  blocks from the model response.
- `sandbox.py`: validates and runs candidate source code in a separate process.
- `laboratorio.py`: runs the `Laboratorio.rodar()` loop. Evaluates the problem baseline
  first, then iteratively requests candidates from the proposer, runs each one in the
  sandbox, scores valid outputs through the problem verifier, caches seen candidates, and
  maintains a bounded bank (`Relatorio.banco`) sorted by score. Stops after `iteracoes`
  rounds or `paciencia` rounds without improvement.
- `cli.py`: implements `arquimedes rodar --problema bin_packing --iteracoes 5`.

## Sandbox layers (`src/arquimedes/sandbox.py`)

Candidate code is generated text and is treated as hostile:

1. **Static AST check (`validar_codigo`)**: parses the candidate with `ast.parse` in the
   main process without executing it. Rejects imports, classes, `global`/`nonlocal`, async
   syntax, names or attributes starting with `_`, frame/code object attributes, and
   dangerous builtins (`eval`, `exec`, `compile`, `open`, `getattr`, `type`, etc.).
   Requires the top-level target function (for example `escolher_bin`) to be defined.
2. **Process isolation (`Sandbox._rodar_filho`)**: writes `runner.py`, `candidato.py`,
   `harness.py`, and `entrada.json` to a temporary directory, then spawns
   `python -I runner.py` with `cwd` set to that directory, `stdin`/`stdout`/`stderr`
   redirected to `DEVNULL`, an empty environment (preserving only `SYSTEMROOT` on Windows
   so the interpreter can start), and a wall-clock timeout.
3. **In-child restrictions (`_RUNNER`)**: sets `RLIMIT_CPU` and `RLIMIT_AS` when `resource`
   is available, poisons networking and process modules in `sys.modules` (`socket`, `ssl`,
   `http`, `urllib`, `subprocess`, `ctypes`, `multiprocessing`, etc.), and executes the
   candidate with a narrow `__builtins__` allowlist.
4. **Independent verification (`BinPackingOnline._contar_bins`)**: the child only writes
   the list of bin assignments to `saida.json`. The parent checks the file size, parses the
   JSON, and replays every item assignment from scratch to verify capacity constraints and
   compute the number of bins.

## Extending

- **New problem**: implement the `Problema` protocol in `problema.py` and register the
  class in `PROBLEMAS`.
- **Real LLM**: pass a `prompt -> str` function to `PropositorLLM(gerar=...)`. Keep the
  process inside a container or VM without network access when evaluating model-generated
  code.
