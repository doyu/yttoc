# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Shared development rules are in global `AGENTS.md`. Repository-specific structure and build commands are in repo-local `AGENTS.md`. This file covers Claude Code-specific context only.

## Project Overview

nbdev-based Python package (`yttoc`) — YouTube Xscript to structured Table of Contents. LLM-driven pipeline that converts video xscripts into searchable, hierarchical knowledge assets. Currently in pre-alpha (v0.0.1).

## Terminology

This project uses **xscript** (not "transcript") to refer to YouTube video transcripts throughout code, docs, and module names.

## nbdev Conventions

- `nbs/00_core.ipynb` → `yttoc/core.py` (via `#| default_exp core`)
- `#| export` marks cells for module export
- `#| hide` excludes cells from docs
- `nbs/index.ipynb` generates `README.md`
- See `docs/implementation-plan.md` for phased roadmap and planned module map
