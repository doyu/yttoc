# Pydantic Phase 2d — AssembledSummaries Design

**Date:** 2026-04-19
**Status:** Approved design, awaiting implementation plan

## Background

Phase 2 pilot (Segment, PRs #14/#15), Phase 2b (NormalizedSection + TocFile, PRs #17/#18), and Phase 2c (Meta, PRs #20/#21) have progressively Pydantic-typed the yttoc pipeline. Phase 2d is the final sub-phase: it models `summaries.json`, completes the type-purity cleanups deferred from Phase 2b (`format_toc_line`) and Phase 2c (`format_header` Union), and brings `yttoc/map.py` and `yttoc/ask.py` consumers into the Pydantic world.

After Phase 2d ships, every internal pipeline shape and every on-disk JSON file in yttoc is Pydantic-validated on I/O and attribute-accessed in consumers.

## Goal

Introduce `AssembledSummaries`, `AssembledSection`, `VideoBlock`, and `FlattenedSection` Pydantic models. Validate `summaries.json` on every read via `AssembledSummaries.model_validate_json`. Write via `.model_dump_json`. Remove the legacy `_migrate_old_summaries` code path (no reachable on-disk cases remain). Purify `format_header` and `format_toc_line` signatures, removing the `| dict` Union shim introduced in Phase 2c and the dict-typed parameter kept in Phase 2b.

## Scope

### In scope
- New Pydantic models: `VideoBlock`, `AssembledSection`, `AssembledSummaries` (in `yttoc.summarize`) and `FlattenedSection` (in `yttoc.map`)
- `_assemble_summaries` constructs `AssembledSummaries`; `generate_summaries` returns `AssembledSummaries`; `get_summaries` returns `AssembledSummaries | dict` (`dict` preserved only for the error branch)
- Strict on-read validation at all 3 summaries.json read sites (`generate_summaries` cache hit, `get_summaries`, `load_summaries`)
- Consumer attribute access in `summarize.py` (`_print_section_summary`, `yttoc_sum`), `ask.py` (`_find_section`, `format_citations`), `map.py` (`load_summaries`, `flatten_sections`, `_build_keyword_index`, `render_by_*`)
- Type purity in `core.py` (`format_header(meta: Meta | VideoBlock)`, `format_toc_line(section: NormalizedSection)`)
- Drop `format_toc_line(s.model_dump(), url)` adapter in `yttoc_toc` (`toc.py`)
- Remove `_migrate_old_summaries` and its test cell (`11e566da`); remove the legacy-detection branch in `generate_summaries`
- Pre-flight script verifies existing cached summaries.json files validate against `AssembledSummaries`

### Out of scope (no future Phase planned)
- Schema versioning in summaries.json
- One-shot migration tool for hypothetical future format changes
- Performance tuning

## Model Hierarchy

```
NormalizedSection (core.py)            [Phase 2b]
        ↑ subclass
AssembledSection (summarize.py)        [new in 2d]
   adds: summary, keywords, evidence
        ↑ subclass
FlattenedSection (map.py)              [new in 2d]
   adds: lesson, video_id, video_title, jump_url

VideoBlock (summarize.py)              [new in 2d]
   id, title, channel, url, duration, upload_date   (6 fields; "url" on-disk, not "webpage_url")

AssembledSummaries (summarize.py)      [new in 2d, envelope]
   video: VideoBlock
   sections: list[AssembledSection]
   full: SectionSummaryPayload         (existing Phase 1 type)
```

### Model definitions

```python
# yttoc/summarize.py
class VideoBlock(BaseModel):
    "Video header subset persisted inside summaries.json."
    id: str = Field(description="YouTube video ID")
    title: str = Field(description="Video title")
    channel: str = Field(description="Channel name")
    url: str = Field(description="Canonical YouTube URL")
    duration: int = Field(ge=0, description="Duration in seconds")
    upload_date: str = Field(description="Upload date in YYYYMMDD format")

class AssembledSection(NormalizedSection):
    "TOC section with LLM-generated summary payload."
    summary: str = Field(description="1-2 sentence summary")
    keywords: list[str] = Field(description="Important terms")
    evidence: Evidence = Field(description="Quoted phrase + timestamp")

class AssembledSummaries(BaseModel):
    "On-disk shape of summaries.json."
    video: VideoBlock
    sections: list[AssembledSection]
    full: SectionSummaryPayload
```

```python
# yttoc/map.py
from yttoc.summarize import AssembledSection

class FlattenedSection(AssembledSection):
    "One row of the cross-video keyword/topic grid."
    lesson: int = Field(ge=1, description="1-based index in the lesson list")
    video_id: str = Field(description="YouTube video ID")
    video_title: str = Field(description="Video title")
    jump_url: str = Field(description="Deep-link URL for the section start")
```

### Placement rationale
- `AssembledSection` and `VideoBlock` live in `yttoc.summarize` because `AssembledSummaries` (the file envelope) owns them, mirroring the `TocFile` / `NormalizedSection` split from Phase 2b (file envelope next to file I/O; element type in the appropriate home).
- Exception: `NormalizedSection` lives in `core` because it is shared across 4+ modules. `AssembledSection` is consumed by `summarize`, `ask`, and `map` — also 3+ modules — but we keep it in `summarize` because it is semantically tied to summaries.json. `map` and `ask` already import from `summarize` transitively via `get_summaries`.
- `FlattenedSection` is map-local; it is never persisted and is only produced/consumed within `map.py`.

### `url` vs `webpage_url` naming divergence
`VideoBlock.url` matches the on-disk key in existing `summaries.json` files (the pre-Pydantic `_assemble_summaries` renamed `meta['webpage_url']` to `video['url']`). We preserve the rename rather than changing the on-disk format — all 17 existing cached `summaries.json` files use `url`. Consumers accept the rename naturally because `Meta` and `VideoBlock` are distinct classes with no inheritance relationship.

## PR Split

Three PRs, selected in Q1:

### PR-A — Models + `_assemble_summaries` internal use (API-preserving, ~60 lines)

Zero consumer impact. `_assemble_summaries` constructs `AssembledSummaries` internally and returns `.model_dump(mode='json')` so `generate_summaries` still writes and returns the same dict shape.

**Changes:**
1. `nbs/04_summarize.ipynb`:
   - Add `VideoBlock`, `AssembledSection`, `AssembledSummaries` BaseModels near the existing `Evidence` / `SectionSummaryPayload` / `SummaryLLMResult` block.
   - Update `_assemble_summaries` body to construct `AssembledSummaries(...)` and return `as.model_dump(mode='json')`.
   - Add validation tests: required fields, `AssembledSection` is a `NormalizedSection` subclass (via `isinstance`), `AssembledSummaries` envelope rejects missing top-level keys.

2. Generated `yttoc/summarize.py`, `yttoc/_modidx.py`.

**Acceptance:**
- All existing tests pass (public API unchanged)
- New validation tests pass
- `from yttoc.summarize import AssembledSummaries, AssembledSection, VideoBlock` works
- `issubclass(AssembledSection, NormalizedSection)` is True

### PR-B — Propagate through `summarize` and `ask`; wrap on-read validation (~150 lines)

Flips public types, switches consumers to attribute access, adds strict on-read validation at the 3 summaries.json read sites, removes `_migrate_old_summaries`.

**Pre-implementation check** (before branching):
```bash
.venv/bin/python <<'PYEOF'
from pathlib import Path
from yttoc.summarize import AssembledSummaries
import sys
fails = []
for f in sorted((Path.home() / '.cache' / 'yttoc').glob('*/summaries.json')):
    try:
        AssembledSummaries.model_validate_json(f.read_text(encoding='utf-8'))
        print(f'OK: {f}')
    except Exception as e:
        fails.append((f, e))
        print(f'FAIL: {f} → {e}')
sys.exit(1 if fails else 0)
PYEOF
```

**Changes:**
1. `nbs/04_summarize.ipynb`:
   - `_assemble_summaries` returns `AssembledSummaries`; drop the trailing `.model_dump(mode='json')`.
   - `generate_summaries` returns `AssembledSummaries`. Replace the 3-branch body (cache-hit legacy detection → new / legacy migration / full build) with a 2-branch body (cache-hit via `AssembledSummaries.model_validate_json` / full build). Remove the `if 'video' in cached: return cached else: _migrate_old_summaries(...)` logic.
   - Remove `_migrate_old_summaries` definition entirely.
   - Writes use `result.model_dump_json(indent=2)`.
   - `get_summaries(video_id, root) -> AssembledSummaries | dict`: reads via `AssembledSummaries.model_validate_json`; error branch still returns a plain `{'error': '...'}` dict.
   - `_print_section_summary(s: AssembledSection, url)`: attribute access for `s.path`, `s.title`, `s.start`, `s.end`, `s.summary`, `s.keywords`, `s.evidence.text`, `s.evidence.at`.
   - `yttoc_sum`: `sums.video`, `sums.sections`, `sums.full` attribute access.
   - Remove Test 7 (cell `11e566da`) — legacy migration test.

2. `nbs/06_ask.ipynb`:
   - `_find_section(sections: list[AssembledSection], seconds: int) -> AssembledSection | None`: attribute access.
   - `format_citations`: `sums.video.title`, `sums.sections`, `s.path`, `s.title` attribute access. The `isinstance(_read_summaries(...), dict)` error-branch check stays — error case still returns dict.

3. Test fixtures: the 4 `_make_test_summaries()` fixtures in `nbs/04_summarize.ipynb` stay as dict literals (they represent on-disk JSON read through `model_validate_json`). Assertions on the return value from `get_summaries`, `generate_summaries`, and CLI output switch to attribute access.

4. Generated `yttoc/summarize.py`, `yttoc/ask.py`, `yttoc/_modidx.py`.

**Acceptance:**
- Pre-flight: all 17 cached summaries.json files validate
- `nbdev-test` full suite green
- Corruption-rejection test: invalid summaries.json raises `ValidationError` at read
- Round-trip smoke test: write → read produces equal `AssembledSummaries` instance
- Legacy Test 7 removed; no reachable code paths through `_migrate_old_summaries`

### PR-C — `map.py` typing + `core.py` type purity (~90 lines)

Completes Phase 2 cleanup.

**Changes:**
1. `nbs/05_map.ipynb`:
   - Add `FlattenedSection(AssembledSection)` with `lesson, video_id, video_title, jump_url`.
   - `load_summaries(ids, root) -> list[AssembledSummaries]`: returns `list[AssembledSummaries]` instead of dict list; attribute access throughout.
   - `flatten_sections(docs: list[AssembledSummaries]) -> list[FlattenedSection]`: constructs `FlattenedSection(...)` rows.
   - `_build_keyword_index(rows: list[FlattenedSection]) -> dict[str, list[tuple[str, FlattenedSection]]]`: attribute access on `row.keywords`.
   - Three renderers (`render_by_topic`, `render_by_keyword`, `render_by_lecture`): attribute access; `format_toc_line(row, url)` no longer needs `.model_dump()` adapter — passes FlattenedSection directly (accepted via NormalizedSection polymorphism).

2. `nbs/00_core.ipynb`:
   - `format_header(meta: Meta | VideoBlock) -> str`: drop `| dict` from signature and drop the `isinstance(meta, dict)` branch; both Meta and VideoBlock expose the 4 attributes used (`title`, `channel`, `duration`, `upload_date`) identically.
   - `format_toc_line(section: NormalizedSection, url: str = '') -> str`: retype from `dict` to `NormalizedSection`; body switches to attribute access. AssembledSection and FlattenedSection are accepted via inheritance polymorphism.

3. `nbs/03_toc.ipynb`:
   - `yttoc_toc` CLI: change `format_toc_line(s.model_dump(), url)` back to `format_toc_line(s, url)` (adapter no longer needed).

4. Generated `yttoc/core.py`, `yttoc/toc.py`, `yttoc/map.py`, `yttoc/_modidx.py`.

**Acceptance:**
- Full `nbdev-test` green
- Grep: no remaining `section[...]` / `section.get(...)` dict-style accesses on `NormalizedSection` subclass values in `yttoc/core.py`, `yttoc/map.py`, `yttoc/summarize.py`, `yttoc/ask.py`, `yttoc/toc.py`
- `format_toc_line` and `format_header` signatures are pure Pydantic types (no `| dict`)
- Integration test: `format_toc_line` accepts `NormalizedSection`, `AssembledSection`, and `FlattenedSection` instances; `format_header` accepts `Meta` and `VideoBlock` instances

## Test Strategy

### PR-A tests
- Valid `AssembledSummaries` construction; missing top-level key raises `ValidationError`
- `AssembledSection` accepts all 7 fields; missing any required field raises
- `issubclass(AssembledSection, NormalizedSection)` is True
- `VideoBlock` accepts 6 fields; negative duration raises; missing field raises

### PR-B tests
- Corruption-rejection: write a summaries.json with a missing section field; `get_summaries` raises `ValidationError`
- Round-trip: `_assemble_summaries(meta, toc, llm) → AssembledSummaries`; `AssembledSummaries.model_validate_json(model.model_dump_json())` yields equal instance
- Existing CLI tests continue to pass with asserted output unchanged (file-write-then-read still produces the same stdout)

### PR-C tests
- Polymorphism integration: `format_toc_line(ns)`, `format_toc_line(as_)`, `format_toc_line(fs)` all produce identical strings for shared fields
- `format_header(meta)` and `format_header(vb)` produce identical strings for shared fields

## Non-Goals

- Schema versioning (no `version` field in models) — YAGNI
- CLI flag to opt out of validation — YAGNI
- Migration tooling for summaries.json shape changes — not needed; pre-flight catches any mismatch, all current caches validate

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Existing cached summaries.json files fail `AssembledSummaries` validation | Pre-flight script in PR-B. If any fail, stop and either migrate or remove. |
| Removing `_migrate_old_summaries` breaks users whose caches are in legacy shape | All 17 current caches are new shape (explorer confirmed); legacy shape is unreachable. Users on older versions who upgrade past a legacy boundary can regenerate via `yttoc-fetch` + `yttoc-sum`. |
| FlattenedSection inheritance from AssembledSection means extra fields get written to disk if ever serialized | FlattenedSection is never persisted — it is an in-memory intermediate. Add an assertion or comment to document this. |
| `format_header(meta: Meta | VideoBlock)` Union is still a Union (just without `dict`); reviewer may still flag it as polymorphism | Reviewer approved Meta | dict in Phase 2c with the same reasoning (2 typed alternatives, isinstance-dispatch in 2 lines). Meta | VideoBlock is strictly tighter. |
| `get_summaries` returning `AssembledSummaries | dict` (error branch stays dict) is mildly asymmetric | Alternative: `get_summaries() -> AssembledSummaries` that raises on error. Rejected because ask.py's tool handler contract expects a dict for errors. Keep the asymmetry. |
| `load_summaries` (map.py) signature change ripples through 4 renderers | All 4 renderers update in the same PR (PR-C). Changes are mechanical `row['x']` → `row.x`. |

## Acceptance Criteria

### PR-A
- [ ] `VideoBlock`, `AssembledSection`, `AssembledSummaries` defined; exports from `yttoc.summarize`
- [ ] `AssembledSection` inherits `NormalizedSection` (confirmed via test)
- [ ] `_assemble_summaries` uses `AssembledSummaries` internally; public return shape unchanged
- [ ] All 4 validation tests pass
- [ ] Full `nbdev-test` green

### PR-B
- [ ] Pre-flight confirms all cached summaries.json files validate
- [ ] `_assemble_summaries` and `generate_summaries` return `AssembledSummaries`
- [ ] `get_summaries` returns `AssembledSummaries | dict`
- [ ] All 3 summaries.json read sites use `AssembledSummaries.model_validate_json`
- [ ] `_print_section_summary`, `yttoc_sum`, `_find_section`, `format_citations` use attribute access
- [ ] `_migrate_old_summaries` and Test 7 removed
- [ ] Legacy-detection branch in `generate_summaries` removed
- [ ] Corruption-rejection test + round-trip smoke test pass
- [ ] Full `nbdev-test` green

### PR-C
- [ ] `FlattenedSection(AssembledSection)` defined in `yttoc.map`
- [ ] `load_summaries`, `flatten_sections`, `_build_keyword_index`, 3 renderers use attribute access
- [ ] `format_header(meta: Meta | VideoBlock)` — `| dict` removed, isinstance branch replaced with dual-attribute access
- [ ] `format_toc_line(section: NormalizedSection)` — dict signature removed
- [ ] `yttoc_toc` drops `.model_dump()` adapter
- [ ] Polymorphism integration test passes
- [ ] Grep: no Pydantic-shape subscript access remains in `yttoc/core.py`, `yttoc/map.py`, `yttoc/summarize.py`, `yttoc/ask.py`, `yttoc/toc.py`
- [ ] Full `nbdev-test` green

## End State

After PR-C merges, yttoc's entire data pipeline is Pydantic-typed end-to-end:
- In-memory types: `Segment`, `NormalizedSection`, `AssembledSection`, `FlattenedSection`
- On-disk files: `TocFile` (toc.json), `Meta` (meta.json), `AssembledSummaries` (summaries.json)
- LLM I/O: `RawTocSection`/`TocLLMResult`, `SummaryLLMResult`, `AskResponse`, `Citation`, `GetSummariesArgs`, `GetXscriptRangeArgs`
- CLI display: `format_header` and `format_toc_line` are strictly Pydantic-typed

Phase 2 is complete; no further Phase 2x spec planned.
