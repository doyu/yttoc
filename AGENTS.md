# Repository Guidelines

This file extends the global `AGENTS.md`. Shared rules (TDD workflow, KISS/YAGNI, coding style, docstrings, commit/PR conventions) are defined there and apply here unchanged.

Below are **yttoc-specific** additions only.

## Project Structure

| Path | Role |
|------|------|
| `nbs/` | Source of truth — Jupyter notebooks |
| `yttoc/` | Auto-generated Python modules (do not hand-edit) |
| `docs/implementation-plan.md` | Phased roadmap, CLI design, module map |
| `scripts/normalize_notebooks.py` | Strips trailing whitespace in notebook cells |
| `.github/workflows/test.yaml` | CI: nbdev-ci on push/PR |
| `.github/workflows/deploy.yaml` | Quarto docs → GitHub Pages on main push |

## Build Commands

All commands require `.venv`:

```bash
source .venv/bin/activate
pip install -e .
python scripts/normalize_notebooks.py nbs/*.ipynb
nbdev-prepare
nbdev-test
```

## Notebook → Module Map

See `docs/implementation-plan.md` § nbdev モジュール対応表 for the full map. Key entries:

| Notebook | Module |
|----------|--------|
| `nbs/01_fetch.ipynb` | `yttoc/fetch.py` |
| `nbs/02_xscript.ipynb` | `yttoc/xscript.py` |
| `nbs/03_toc.ipynb` | `yttoc/toc.py` |
| `nbs/04_summarize.ipynb` | `yttoc/summarize.py` |

## Testing Notes

- Network-dependent tests use `#| eval: false` to skip in CI
- `nbdev-test` runs from `nbs/`, so relative paths like `solveit2.txt` resolve there
