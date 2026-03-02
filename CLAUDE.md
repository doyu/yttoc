# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

nbdev-based Python package (`settings`) — a meal tracking web app with AI-driven nutritional analysis (FastHTML + HTMX + OpenAI). Currently in pre-alpha (v0.0.1), scaffold only.

## Development Commands

All commands require the `.venv` environment:

```bash
source .venv/bin/activate
pip install -e .                              # Install in dev mode
python scripts/normalize_notebooks.py nbs/*.ipynb  # Normalize notebooks before commit
nbdev_prepare                                 # Export notebooks → Python modules + docs
nbdev_test                                    # Run tests
```

## Architecture

| Path | Role |
|------|------|
| `nbs/` | Source of truth — Jupyter notebooks (edit here) |
| `settings/` | Auto-generated Python package from `nbs/` via nbdev |
| `scripts/normalize_notebooks.py` | Strips trailing whitespace in notebook cells |
| `settings.ini` | nbdev master config (version, paths, metadata) |
| `.github/workflows/test.yaml` | CI: `answerdotai/workflows/nbdev-ci` on push/PR |
| `.github/workflows/deploy.yaml` | Quarto docs → GitHub Pages on main push |

### nbdev Conventions

- `nbs/00_core.ipynb` → `settings/core.py` (via `#| default_exp core`)
- `#| export` marks cells for module export
- `#| hide` excludes cells from docs
- `nbs/index.ipynb` generates `README.md`
- New features go in new numbered notebooks (e.g., `01_feature.ipynb`)

### Workflow

1. Edit notebooks in `nbs/`
2. `scripts/normalize_notebooks.py nbs/*.ipynb`
3. `nbdev_prepare`
4. `nbdev_test`
5. Stage both `nbs/` and generated `settings/` files
6. PR to main (1 PR = 1 feature, ≈ under 200 lines)
