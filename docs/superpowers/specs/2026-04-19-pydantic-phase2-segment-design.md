# Pydantic Phase 2 — Segment Pilot Design

**Date:** 2026-04-19
**Status:** Approved design, awaiting implementation plan

## Background

Phase 1 (PR #13, merged 2026-04-19) replaced hand-written JSON Schema dicts with Pydantic `model_json_schema()` as the single schema source for LLM Structured Outputs (toc, summarize, ask). Phase 1 explicitly deferred "internal dict shapes" — the `Segment`, `NormalizedSection`, `Meta`, and `AssembledSummaries` dicts that flow between pipeline stages — to Phase 2.

Phase 2 is split into sub-phases by shape. This spec covers the **pilot**: `Segment`.

## Goal

Replace the in-memory segment dict produced by `parse_xscript()` with a Pydantic `Segment` model. Propagate the type through all pipeline consumers. Validate that the "Pydantic = single type source" pattern holds when applied to internal data, not just LLM I/O.

## Scope

### In scope
- `Segment` Pydantic model with `start`, `end`, `text` fields and `ge=0` bounds on timestamps
- `parse_xscript()` returns `list[Segment]`
- All downstream consumers updated to attribute access: `slice_segments`, `_build_toc_prompt`, `_build_summary_prompt`, `get_xscript_range`, CLI display helpers
- `dispatch_tool` in `ask.py` gains Pydantic-aware serialization at the LLM tool boundary
- Test fixtures in `nbs/02_xscript.ipynb` migrated to `Segment(...)` constructors

### Out of scope (deferred Phase 2 sub-phases)
- **Phase 2b**: `NormalizedSection` (toc.json) Pydantic-ization + on-read validation
- **Phase 2c**: `Meta` (meta.json) Pydantic-ization
- **Phase 2d**: `AssembledSummaries` (summaries.json) Pydantic-ization
- **Non-goal**: `FlattenedSection` and `KeywordIndex` in `map.py` — internal to one module, no cross-module flow; YAGNI

## PR Split

Two PRs to keep each under the AGENTS.md 200-line guideline and to isolate risk.

### PR #1 — Model introduction (low risk, ~30 lines)

Introduce `Segment` without changing the public API.

**Files**
| File | Change |
|------|--------|
| `nbs/02_xscript.ipynb` | Add `from pydantic import BaseModel, Field` to imports. Define `Segment` BaseModel. Inside `parse_xscript`, construct `Segment(...)` objects and return `[s.model_dump() for s in segments]`. |
| `yttoc/xscript.py` | Regenerated via `nbdev-export`. |

**Model definition**
```python
class Segment(BaseModel):
    "One parsed xscript segment (in-memory)."
    start: float = Field(ge=0, description="Start time in seconds")
    end: float = Field(ge=0, description="End time in seconds")
    text: str = Field(description="Normalized cue text")
```

**Effect**
- `parse_xscript` public signature unchanged: still returns `list[dict]`
- Internal Pydantic validation catches negative timestamps (which `_ts_to_sec` cannot produce today, but the constraint documents the invariant)
- Downstream consumers untouched

**Tests**
- All existing `nbs/02_xscript.ipynb` tests must pass unchanged
- Add a Pydantic validation test: `Segment(start=-1, end=0, text="x")` raises `ValidationError`

### PR #2 — Downstream propagation (~150 lines)

Flip the public API to `list[Segment]` and update all consumers.

**Files**
| File | Change |
|------|--------|
| `nbs/02_xscript.ipynb` | `parse_xscript` returns `list[Segment]` (drop `.model_dump()`). Migrate the 16 inline dict fixtures to `Segment(...)` constructors. |
| `nbs/00_core.ipynb` | `slice_segments(segments: list[Segment], start, end) -> list[Segment]`. Switch `s['start']` to `s.start`. |
| `nbs/03_toc.ipynb` | `_build_toc_prompt(segments: list[Segment], meta)`: attribute access in loop. |
| `nbs/04_summarize.ipynb` | `_build_summary_prompt`: attribute access. `slice_segments` call sites updated. |
| `nbs/06_ask.ipynb` | `dispatch_tool`: add `_to_jsonable` helper; apply to `result` before `json.dumps`. `get_xscript_range` returns `list[Segment]` (via `parse_xscript`). |
| `nbs/02_xscript.ipynb` (CLI) | `yttoc_raw` display loop (`yttoc/xscript.py:155-157`) and `yttoc_txt` (`yttoc/xscript.py:178`): `s['start']` / `s['text']` → `s.start` / `s.text`. |
| Generated `yttoc/*.py` | Regenerated via `nbdev-export`. |

**Exactly 5 xscript-segment consumer sites** to update (verified by grep — filtered out NormalizedSection / AssembledSummaries consumers which are out of scope):
1. `yttoc/core.py:32` — `slice_segments` filter
2. `yttoc/toc.py:51-53` — `_build_toc_prompt` loop
3. `yttoc/summarize.py:26-28` — `_build_summary_prompt` loop
4. `yttoc/xscript.py:155-157` — `yttoc_raw` CLI print
5. `yttoc/xscript.py:178` — `yttoc_txt` CLI print

**Tool-boundary helper**
```python
def _to_jsonable(o):
    if isinstance(o, BaseModel): return o.model_dump()
    if isinstance(o, list): return [_to_jsonable(x) for x in o]
    if isinstance(o, dict): return {k: _to_jsonable(v) for k, v in o.items()}
    return o
```

Applied inside `dispatch_tool` before `json.dumps`. This keeps the LLM tool contract ("return JSON-serializable data to the model") intact while allowing handlers to return Pydantic models internally. Handlers that already return dicts are unaffected (`_to_jsonable` is idempotent for dicts).

**Tests**
- All existing tests pass after fixture migration
- `_to_jsonable` unit test: covers `BaseModel`, `list[BaseModel]`, nested dict containing `BaseModel`, passthrough for plain dict/list/str/int

## Validation Constraints

Minimal, following Phase 1 precedent:
- `start: float = Field(ge=0)` — timestamps non-negative
- `end: float = Field(ge=0)` — same
- `text: str` — no `min_length` constraint (empty-text cues are already filtered in `parse_xscript`)
- **Not added**: `end >= start` cross-field validator. SRT semantics guarantee it; adding the validator would duplicate the guarantee with no caught bugs. YAGNI.

## Test Fixture Strategy

PR #2 rewrites the 16 segment fixtures in `nbs/02_xscript.ipynb` from:
```python
{"start": 0.08, "end": 4.88, "text": "hello world"}
```
to:
```python
Segment(start=0.08, end=4.88, text="hello world")
```

Rationale: PR #2's theme is "Segment-as-type throughout". Keeping fixtures as dicts would force every assert to call `.model_dump()` or `Segment.model_validate(...)`, creating per-site noise. Full migration is ~16 lines of churn concentrated in one notebook.

## Non-Goals

- **Retroactive validation of old cache files.** If an existing `toc.json` / `summaries.json` on disk has a shape mismatch, no behavioral change in this pilot — those shapes are not touched.
- **Performance.** Pydantic v2 is fast enough; no benchmarking required for this scope.
- **Public Python API stability.** `yttoc` is pre-alpha (v0.0.1). Breaking `parse_xscript`'s return type is acceptable.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| PR #2 touches 5 notebooks — merge conflict exposure | Land PR #1 and PR #2 back-to-back; no parallel branches on the same files |
| Fixture migration introduces typos | Fixture diffs are mechanical; run `nbdev-test` on each notebook after edit |
| `dispatch_tool` change could affect existing dict-returning tools | `_to_jsonable` is idempotent on plain dicts; covered by unit test |
| Pydantic v2 strict-mode surprises (e.g., `int` accepted for `float`) | Explicit `float` fields match existing runtime behavior; no strict mode enforcement needed |

## Acceptance Criteria

### PR #1
- [ ] `Segment` model defined with `ge=0` bounds
- [ ] `parse_xscript` uses `Segment` internally
- [ ] Public return shape unchanged (`list[dict]`)
- [ ] All `nbs/02_xscript.ipynb` existing tests pass
- [ ] Negative-timestamp validation test added and passes (constructor-level, not parser-level — `_ts_to_sec` cannot produce negatives, so the test exercises the Pydantic constraint itself: `Segment(start=-1, ...)` raises `ValidationError`)
- [ ] `nbdev-test` suite green

### PR #2
- [ ] `parse_xscript` returns `list[Segment]`
- [ ] All 16 test fixtures migrated to `Segment(...)`
- [ ] `slice_segments`, `_build_toc_prompt`, `_build_summary_prompt`, `get_xscript_range`, CLI display converted to attribute access
- [ ] `_to_jsonable` helper added to `dispatch_tool`
- [ ] `_to_jsonable` unit test passes
- [ ] Full `nbdev-test` suite green (all notebooks)
- [ ] No `s['start']` / `s['end']` / `s['text']` accesses remain in yttoc modules (verify via grep)

## Follow-up work (separate specs)

- `2026-MM-DD-pydantic-phase2b-normalized-section-design.md` — toc.json validation + NormalizedSection type
- `2026-MM-DD-pydantic-phase2c-meta-design.md` — meta.json validation + Meta type
- `2026-MM-DD-pydantic-phase2d-assembled-summaries-design.md` — summaries.json validation + AssembledSummaries type
