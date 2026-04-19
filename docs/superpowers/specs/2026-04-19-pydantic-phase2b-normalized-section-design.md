# Pydantic Phase 2b — NormalizedSection / toc.json Design

**Date:** 2026-04-19
**Status:** Approved design, awaiting implementation plan

## Background

Phase 2 pilot (`Segment`, PRs #14 and #15) validated the "Pydantic propagates through the pipeline" pattern on an in-memory shape. Phase 2b applies the same pattern to `NormalizedSection` — the TOC section dict `{path, title, start, end}` that `_normalize_sections` produces and that persists to `toc.json`.

This is the first Phase 2 sub-phase that touches an on-disk file format. The design therefore adds an envelope model (`TocFile`) to validate the whole `toc.json` document on read, not just its elements.

## Goal

Replace the `NormalizedSection` dict with a Pydantic model, validate `toc.json` on read/write via a `TocFile` envelope model, and propagate the type through every TOC-section consumer in the pipeline.

## Scope

### In scope
- `NormalizedSection` Pydantic model in `nbs/00_core.ipynb` (shared type)
- `TocFile` Pydantic model in `nbs/03_toc.ipynb` (file envelope)
- `_normalize_sections` switched to `list[NormalizedSection]` output
- `_call_llm` (toc.py) switched to `list[RawTocSection]` output (complete Pydantic chain within the toc module)
- `toc.json` read/write via `TocFile.model_validate_json` / `TocFile.model_dump_json`
- Consumer attribute-access migration in:
  - `yttoc/toc.py` — `_normalize_sections`, `generate_toc`, `yttoc_toc`
  - `yttoc/xscript.py` — `_load_segments` (reads `toc.json` for `--section` lookup)
  - `yttoc/summarize.py` — `_build_summary_prompt`, `_assemble_summaries` (both take TOC sections from `toc.json`)
- Test migration in `nbs/03_toc.ipynb` (Tests 1-5: `RawTocSection(...)` constructors; Tests 7-8: attribute-access assertions on `generate_toc` return) and `nbs/04_summarize.ipynb` Test 3 (`c1000009`: `NormalizedSection(...)` for `sections` fixture)
- Strict on-read validation: `TocFile.model_validate_json` raises `ValidationError` on corrupted files

### Out of scope (deferred sub-phases)
- **Phase 2c**: `Meta` (`meta.json`) Pydantic-ization
- **Phase 2d**: `AssembledSummaries` (`summaries.json`) Pydantic-ization, including the section type used inside `summaries.json` (which extends `NormalizedSection` with `summary`, `keywords`, `evidence`)
- **`_find_section` in `yttoc/ask.py`** — operates on summaries.json sections (Phase 2d territory)
- **`yttoc/map.py`** consumers — same reason, read from summaries.json
- **`format_toc_line` in `yttoc/core.py`** — called from both `toc.py` (NormalizedSection caller, post-PR-B) AND `summarize.py` (summaries.json section, Phase 2d territory). Retyping it in Phase 2b would force an unnatural `NormalizedSection(...)` construction at the summarize.py call site. Phase 2d will unify by having `AssembledSection` subclass `NormalizedSection`, enabling `format_toc_line(section: NormalizedSection)` to accept both via subclass polymorphism.

## Models

### `NormalizedSection` — in `nbs/00_core.ipynb` / `yttoc/core.py`

```python
class NormalizedSection(BaseModel):
    "One TOC section after normalization (path and end added to raw LLM output)."
    path: str = Field(description="Section path like '1', '2', ...")
    title: str = Field(description="Concise English section title")
    start: int = Field(ge=0, description="Start time in integer seconds")
    end: int = Field(ge=0, description="End time in integer seconds")
```

**Placement rationale:** `NormalizedSection` is a shared pipeline type consumed by `core.py`, `xscript.py`, `summarize.py`, and `toc.py`. Placing it in `toc.py` creates a circular import (toc already depends on xscript via `parse_xscript`, and xscript would need to import the type from toc). Placing it in `core.py` mirrors the decision made for `Segment` in the pilot and keeps dependencies unidirectional.

### `TocFile` — in `nbs/03_toc.ipynb` / `yttoc/toc.py`

```python
class TocFile(BaseModel):
    "On-disk shape of toc.json."
    sections: list[NormalizedSection]
```

**Placement rationale:** `TocFile` is a file-I/O concern specific to the toc module. It imports `NormalizedSection` from `core`, but is only used inside `toc.py` (for write) and `xscript.py` (for read via `TocFile.model_validate_json`). Keeping it next to `generate_toc` makes the file-schema/file-I/O pairing obvious.

## PR Split

Follows the Phase 2 pilot's 2-PR pattern for risk isolation and review-size management.

### PR-A — Model introduction (API-preserving, ~40 lines)

Public `generate_toc` return shape stays `list[dict]`. `toc.json` on-disk format stays identical. Zero consumer impact.

**Changes:**
1. `nbs/00_core.ipynb` — add `NormalizedSection` BaseModel + validation test (constructor-level: negative timestamps raise `ValidationError`; missing required field raises `ValidationError`).
2. `nbs/03_toc.ipynb`:
   - Add `TocFile` BaseModel + validation test (missing `sections` key raises `ValidationError`; wrong element shape raises).
   - Switch `_call_llm` return to `list[RawTocSection]` (drop the trailing `.model_dump()` conversion). This is a toc-module-internal change; `_call_llm` is not exported.
   - Switch `_normalize_sections(raw: list[RawTocSection], duration: int) -> list[dict]`. Internally attribute-access `raw[i].title` / `raw[i].start`. Construct `NormalizedSection(...)` instances. Return `[s.model_dump() for s in result]` to preserve the public `list[dict]` contract.
   - Migrate Tests 1-5 input fixtures in `nbs/03_toc.ipynb` from `{'title': ..., 'start': ...}` dict literals to `RawTocSection(...)` constructors (~9 literals across the 5 cells).
3. Generated `yttoc/core.py` and `yttoc/toc.py` auto-regenerated by `nbdev-export`.

**Acceptance:**
- All existing tests pass (public API unchanged)
- New validation tests pass
- `from yttoc.core import NormalizedSection` and `from yttoc.toc import TocFile` succeed

### PR-B — Propagation + file validation + test migration (~130-150 lines)

Flip public types; every consumer switches to attribute access; `toc.json` I/O wrapped in `TocFile`.

**Changes:**

1. **`nbs/03_toc.ipynb`**:
   - `_normalize_sections` return annotation `list[dict]` → `list[NormalizedSection]`; drop trailing `[s.model_dump() for s in _]`.
   - `generate_toc` return annotation `list[dict]` → `list[NormalizedSection]`.
   - File write: replace `json.dumps({'sections': sections}, ...)` with `TocFile(sections=sections).model_dump_json(indent=2)`.
   - Cache-hit read: replace `json.loads(toc_path.read_text())['sections']` with `TocFile.model_validate_json(toc_path.read_text()).sections`.
   - `yttoc_toc` CLI: `format_toc_line(s, url)` call site — `s` is now `NormalizedSection`, no change at the call site (the function adapts). Any direct subscript on a NormalizedSection inside `yttoc_toc` → attribute access.
   - Tests 7-8 assertions on the `generate_toc` return value: rewrite `sections[i]['path']` → `sections[i].path` (~4 sites). The toc.json file-write fixtures themselves remain dict literals (they represent on-disk JSON, not Python data flow).

2. **`nbs/02_xscript.ipynb`**:
   - `_load_segments`: toc.json read becomes `TocFile.model_validate_json(toc_path.read_text()).sections`. `sec_info: NormalizedSection | None = next((s for s in sections if s.path == section), None)`. Switch the three `sec_info[...]` subscripts in the display path (`yttoc_raw` / `yttoc_txt`) to attribute access.

3. **`nbs/04_summarize.ipynb`**:
   - `_build_summary_prompt(segments, sections: list[NormalizedSection], meta)`: switch `sec['start']`, `sec['end']`, `sec['path']`, `sec['title']` to attribute access (~5 sites).
   - `_assemble_summaries(meta, toc_sections: list[NormalizedSection], llm_result)`: switch the ~3 `sec['path']` / `sec['title']` / `sec['start']` / `sec['end']` accesses to attribute access where toc_sections is used. The function still outputs a dict (AssembledSummaries is Phase 2d) — merge via `s.model_dump()` where the function currently spreads dict fields.
   - Migrate Test 3 fixture `sections = [{...}, {...}]` in cell `c1000009` to `NormalizedSection(...)` constructors (2 literals).
   - `_print_section_summary(s: dict, url)` in summarize.py — UNTOUCHED. Its `s` argument is a summaries.json section (Phase 2d territory), not a NormalizedSection. Its `format_toc_line(s, url)` call also stays as-is since `format_toc_line` is out of scope.

4. Generated `yttoc/*.py` auto-regenerated.

**Acceptance:**
- Full `nbdev-test` green
- `TocFile.model_validate_json` invoked in both read sites
- No `sec[...]` / `s[...]` subscript accesses on **NormalizedSection** values in `yttoc/toc.py`, `yttoc/xscript.py`, `yttoc/summarize.py`. Exceptions expected to remain:
  - `yttoc/core.py` `format_toc_line` body — out of scope (still dict-typed per §Out of scope)
  - `yttoc/summarize.py` `_print_section_summary` body — out of scope (summaries.json section input)
  - `yttoc/summarize.py` `_assemble_summaries` accesses on the LLM-result dict (not `toc_sections`) — out of scope
- `yttoc/ask.py` and `yttoc/map.py` are untouched (out of scope)

### Pre-implementation check (before starting PR-B)

Run a sanity check on any real cached `toc.json` files to ensure the shape matches `TocFile` exactly:

```bash
for f in ~/.cache/yttoc/*/toc.json; do
  [ -f "$f" ] && python -c "
from yttoc.toc import TocFile
import sys
try:
    TocFile.model_validate_json(open('$f').read())
    print('OK: $f')
except Exception as e:
    print('FAIL: $f →', e)
"
done
```

If any existing cache fails to validate, stop and investigate before shipping PR-B. Options: fix the model to match reality, or write a one-shot migration to rewrite cached files. We expect all current caches to pass since the shape has been stable.

## Test Strategy

### PR-A tests
- `NormalizedSection` constructor: valid construction; negative `start` / `end` raises `ValidationError`; missing required field raises.
- `TocFile` envelope: missing `sections` key raises; wrong element shape (e.g., `{"sections": [{"no_path": "x"}]}`) raises.
- Tests 1-5 in nbs/03 continue to pass after input fixtures switch from dict to `RawTocSection(...)`.

### PR-B tests
- `TocFile.model_validate_json` rejects a deliberately corrupted file (e.g., `{"sections": [{"path": "1", "title": "t", "start": -1, "end": 10}]}` raises).
- Happy-path smoke test: write a `TocFile`-shaped toc.json to a temp dir, call `generate_toc(video_id)` expecting a cache-hit, assert the returned `list[NormalizedSection]` has the expected paths/titles/starts/ends.

## Validation Constraints

- `path: str` — required, no length constraint (`"1"`, `"2"`, etc.). No pattern enforcement (YAGNI).
- `title: str` — required, no length constraint (consistent with `Segment.text`).
- `start: int = Field(ge=0)` — required, non-negative.
- `end: int = Field(ge=0)` — required, non-negative.
- **Not added:** `end >= start` cross-field validator. `_normalize_sections` already enforces this via `end = next_start` assignment; adding a validator would duplicate the invariant.

## Non-Goals

- Schema versioning in `toc.json` (no `version` field, no migration scaffold) — YAGNI for pre-alpha.
- On-write validation roundtrip test (read-back the file and compare) — the `TocFile` envelope guarantees shape at write; a separate test would be redundant with PR-A's `TocFile` constructor test plus PR-B's cache-hit smoke test.
- Performance tuning for large toc.json files — typical files have <20 sections; Pydantic v2 validation is negligible.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Existing cached `toc.json` files fail validation after PR-B | Pre-implementation check script (above) runs before PR-B branches off. If any fail, stop and fix the model or migrate caches. |
| `_assemble_summaries` now receives `list[NormalizedSection]` but its dict-construction code (for the AssembledSummaries output) may access fields it expects to unpack into the result dict | Update the unpacking to use `s.model_dump()` when merging section data into the summaries.json dict. Phase 2d will clean this up further. |
| PR-B's `xscript.py` changes touch `_load_segments` which was already migrated in Phase 2 pilot | Only the toc.json read portion changes; the segments display loops (already on `Segment`) stay untouched. |
| Scope creep toward Phase 2d (AssembledSummaries) | Keep `ask.py` and `map.py` explicitly untouched; they read summaries.json sections which have a different (wider) shape than `NormalizedSection`. |

## Acceptance Criteria

### PR-A
- [ ] `NormalizedSection` model defined in `nbs/00_core.ipynb`, exports from `yttoc.core`
- [ ] `TocFile` model defined in `nbs/03_toc.ipynb`, exports from `yttoc.toc`
- [ ] `_call_llm` returns `list[RawTocSection]`
- [ ] `_normalize_sections` uses `NormalizedSection` internally, returns `list[dict]` (public API preserved)
- [ ] Tests 1-5 in nbs/03 migrated to `RawTocSection(...)` input fixtures
- [ ] All validation tests pass; full `nbdev-test` green
- [ ] `generate_toc` public return shape unchanged

### PR-B
- [ ] Pre-check script confirms existing cached `toc.json` files validate against `TocFile`
- [ ] `_normalize_sections` and `generate_toc` return `list[NormalizedSection]`
- [ ] `toc.json` written via `TocFile(sections=...).model_dump_json(indent=2)`
- [ ] `toc.json` read via `TocFile.model_validate_json(...).sections` in both `toc.py` and `xscript.py`
- [ ] All 3 in-scope consumer sites (xscript `_load_segments`, summarize `_build_summary_prompt`, summarize `_assemble_summaries`-toc-sections-path) switched to attribute access
- [ ] Tests 7-8 in nbs/03 assertions migrated; Test 3 in nbs/04 `sections` fixture migrated
- [ ] Corruption-rejection test passes
- [ ] Full `nbdev-test` green
- [ ] No remaining NormalizedSection subscript access in `yttoc/toc.py`, `yttoc/xscript.py`, or `yttoc/summarize.py` (verify via grep; `core.py` `format_toc_line` and `summarize.py` `_print_section_summary` / LLM-result accesses remain untouched per §Out of scope)

## Follow-up work (separate specs)

- `2026-MM-DD-pydantic-phase2c-meta-design.md` — Meta (meta.json) Pydantic-ization
- `2026-MM-DD-pydantic-phase2d-assembled-summaries-design.md` — AssembledSummaries (summaries.json) Pydantic-ization, will include the typed section inside summaries (extends `NormalizedSection`) and bring `_find_section` / `map.py` consumers into the Pydantic world.
