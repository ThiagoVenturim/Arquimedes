# Contributing to Arquimedes

Rules:

- No emoji anywhere (code, docs, CLI output, or commits).
- No AI co-author trailers in commits. Run `git config core.hooksPath .githooks` after cloning.
- Work on `develop` or a feature branch and open pull requests against `develop`.
- All tests must run offline without network access or API keys.
- Never evaluate or execute candidate code in the main process; every candidate must go
  through `arquimedes.sandbox.Sandbox`.

Before committing, run:

```bash
ruff check .
python -m pytest
python scripts/check_no_emoji.py
```
