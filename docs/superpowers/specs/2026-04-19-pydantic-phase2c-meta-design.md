# Pydantic Phase 2c — Meta / meta.json Design

**Date:** 2026-04-19
**Status:** Approved design, awaiting implementation plan

## Background

Phase 2 pilot (Segment, PRs #14/#15) and Phase 2b (NormalizedSection + TocFile, PRs #17/#18) established the "Pydantic propagates through the pipeline" pattern for in-memory types and for the TOC on-disk file. Phase 2c extends the pattern to `Meta` — the per-video metadata dict produced by `_build_meta` and persisted as `meta.json`.

Meta has the widest consumer fan-out of any internal shape in yttoc (5+ modules read it). Phase 2c is therefore the largest of the Phase 2 sub-phases, though individual sites each involve only a handful of attribute-access rewrites.

## Goal

Replace the `Meta` dict with a Pydantic model. Validate every `meta.json` read via `Meta.model_validate_json`. Write via `Meta.model_dump_json`. Promote `last_used_at` from ISO string to `datetime`. Constrain `captions` values to `Literal["auto", "manual"]`.

## Scope

### In scope
- `Meta` Pydantic model in `nbs/00_core.ipynb` (shared pipeline type)
- `_build_meta` (fetch.py) constructs `Meta` and returns it
- `_update_last_used` (fetch.py) reads/mutates/writes via Meta
- All 7 `meta.json` read sites switch to `Meta.model_validate_json`
- All consumer `.get('key')` accesses switch to `.key` attribute access
- `format_header(meta: Meta)` in core.py retyped
- 8 test fixtures in `nbs/01_fetch.ipynb`, `nbs/03_toc.ipynb`, `nbs/04_summarize.ipynb` migrated to `Meta(...)` constructors (or appropriate JSON dict when representing on-disk content)
- Pre-flight script validates existing cached `meta.json` files before PR-B branches

### Out of scope (deferred to Phase 2d)
- `summaries.json` `video` block inside `AssembledSummaries` — shares a subset of Meta fields but is a distinct type (Phase 2d will define `AssembledSummaries` with a typed `video` sub-model)
- `yttoc/map.py` consumers of the `video` block (operate on AssembledSummaries, Phase 2d)
- `format_toc_line` in core.py and `_print_section_summary` in summarize.py (already out of scope since Phase 2b; unchanged here)
- `_find_section` in ask.py (summaries.json territory)
- One-shot migration tooling for old caches (pre-flight confirms all existing caches pass; if any fail, address case-by-case)

## Model

### `Meta` — in `nbs/00_core.ipynb` / `yttoc/core.py`

```python
from datetime import datetime
from typing import Literal

class Meta(BaseModel):
    "Cached video metadata (one per cached video; persisted as meta.json)."
    id: str = Field(description="YouTube video ID")
    title: str = Field(description="Video title")
    channel: str = Field(description="Channel name")
    duration: int = Field(ge=0, description="Duration in seconds")
    upload_date: str = Field(description="Upload date in YYYYMMDD format")
    webpage_url: str = Field(description="Canonical YouTube URL")
    description: str = Field(default='', description="Video description (may be empty)")
    captions: dict[str, Literal["auto", "manual"]] = Field(
        description="Caption availability map: lang code → caption type")
    last_used_at: datetime = Field(description="Last cache access time (UTC)")
```

**Field decisions:**
- `description`: defaulted to `''` (mirrors `_build_meta`'s `info.get('description', '')`).
- `duration`: `ge=0` consistent with Segment/NormalizedSection precedent.
- `upload_date`: kept as `str` (YYYYMMDD format). Not promoted to `date` because yt-dlp returns this exact string and all downstream display code treats it as an opaque string. Adding a format pattern is YAGNI.
- `captions`: `Literal["auto", "manual"]` constrains the value space. Pre-flight script verifies no existing cache has other values. If yt-dlp later returns other caption types (e.g., `"srt_file_found"`), update the Literal union.
- `last_used_at`: `datetime`. Pydantic v2 parses ISO 8601 strings natively via `datetime.fromisoformat`-compatible logic. Serialization via `model_dump_json` produces RFC 3339-style output. Existing cache format `"2026-04-16T15:13:50.653895+00:00"` parses cleanly; output format matches (verified in pre-flight).

**Placement rationale:** Meta is consumed by fetch, toc, summarize, xscript, core, map. Placing it in `core.py` mirrors the decision for Segment and NormalizedSection and keeps dependencies unidirectional (`fetch → core`, `toc/summarize/xscript → core`). No `MetaFile` envelope is needed because `meta.json` is a flat dict, not an envelope-wrapped structure.

## PR Split

Two PRs, mirroring Phase 2 pilot and Phase 2b.

### PR-A — Model introduction (API-preserving, ~40 lines)

Public `_build_meta` return shape stays `dict`. Zero consumer impact.

**Changes:**
1. `nbs/00_core.ipynb`: add `from datetime import datetime`, `from typing import Literal`, and `Meta` BaseModel. Add validation test covering: missing required field, negative `duration`, invalid `captions` value, invalid `last_used_at` string.
2. `nbs/01_fetch.ipynb`: import `Meta` from `yttoc.core`. Inside `_build_meta`, construct `Meta(...)` and return `meta.model_dump(mode='json')`. The `mode='json'` parameter ensures `datetime` is serialized to an ISO string (so downstream consumers that still call `json.dumps(meta)` work unchanged).

**Acceptance:**
- All existing tests pass (public API unchanged)
- New validation tests pass
- `from yttoc.core import Meta` works

### PR-B — Propagation + file validation + test migration (~170-190 lines)

Flip public types; every consumer switches to attribute access; meta.json I/O wraps through `Meta.model_validate_json` / `Meta.model_dump_json`.

**Changes:**

1. **`nbs/01_fetch.ipynb`**:
   - `_build_meta` return annotation `dict` → `Meta`; drop `.model_dump(mode='json')` at the end.
   - `fetch_video` write path: `meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))` → `meta_path.write_text(meta.model_dump_json(indent=2))`.
   - `_update_last_used`: switch body to `meta = Meta.model_validate_json(meta_path.read_text(...))`; `meta.last_used_at = datetime.now(timezone.utc)`; `meta_path.write_text(meta.model_dump_json(indent=2))`.
   - `yttoc_list`: read via `Meta.model_validate_json`; `meta.get('captions', {})` → `meta.captions`; `meta.get('last_used_at', '')` → `meta.last_used_at.isoformat()` (for display-only rendering).

2. **`nbs/00_core.ipynb`**:
   - `format_header(meta: Meta)` signature update; the 4 subscript accesses (`meta.get('title', '')`, etc.) become attribute access.

3. **`nbs/02_xscript.ipynb`**:
   - `_load_segments`: `json.loads(meta_path.read_text())` → `Meta.model_validate_json(...)`; update the tuple return annotation `tuple[dict, list[Segment], NormalizedSection | None, Path]` → `tuple[Meta, list[Segment], NormalizedSection | None, Path]`.

4. **`nbs/03_toc.ipynb`**:
   - `generate_toc` and `yttoc_toc`: `json.loads(meta_path.read_text())` → `Meta.model_validate_json(...)`; `meta.get('duration', 0)` → `meta.duration` (no default needed; Meta enforces the field).
   - `_build_toc_prompt(segments: list[Segment], meta: Meta) -> str`: signature update; the 3 `meta.get('title')` / `meta.get('channel')` / `meta.get('description')` accesses become attribute access.

5. **`nbs/04_summarize.ipynb`**:
   - `generate_summaries` and `_migrate_old_summaries`: `json.loads(meta_path.read_text())` → `Meta.model_validate_json(...)`.
   - `_build_summary_prompt(segments, sections, meta: Meta) -> str`: signature update; 3 accesses switch.
   - `_assemble_summaries(meta: Meta, toc_sections, llm_result) -> dict`: signature update. The output `'video'` block construction reads `meta.id`, `meta.title`, `meta.channel`, `meta.webpage_url`, `meta.duration`, `meta.upload_date` — still builds a raw dict for on-disk `summaries.json` (AssembledSummaries remains dict-typed in Phase 2c; Phase 2d will type it).

6. **Test fixture migration** — 8 cells total:
   - `nbs/01_fetch.ipynb` cells `vcljbltw9ym` and `6051a34b`: migrate fake `info` dicts passed to `_build_meta` (still dict, not Meta — mimics yt-dlp input) and migrate pre-written `meta.json` content (either `Meta(...).model_dump_json(indent=2)` or explicit dict matching Meta shape, whichever is clearer per cell).
   - `nbs/03_toc.ipynb` cells `971d3b0c`, `f0fb87b4`: the pre-written `meta.json` dicts — leave as JSON dict literals since they represent on-disk bytes read via `Meta.model_validate_json`. Verify all 9 required fields present (add any missing — current fixtures may omit `captions` and assume downstream `.get('captions', {})` — after Phase 2c they must include `captions` to satisfy Meta validation).
   - `nbs/04_summarize.ipynb` cells `aa6db3d2`, `87bf3d0d`: same pattern — ensure fixtures contain all 9 Meta fields.

**Generated files** (auto-regenerated via `nbdev-export`): `yttoc/core.py`, `yttoc/fetch.py`, `yttoc/xscript.py`, `yttoc/toc.py`, `yttoc/summarize.py`, `yttoc/_modidx.py`.

### Pre-implementation check (before PR-B)

Run against existing cache before branching:

```bash
/home/doyu/yttoc/.venv/bin/python <<'PY'
from pathlib import Path
from yttoc.core import Meta
import sys
fails = []
for f in sorted((Path.home() / '.cache' / 'yttoc').glob('*/meta.json')):
    try:
        m = Meta.model_validate_json(f.read_text(encoding='utf-8'))
        # Extra guard: confirm caption values are the Literal set
        for lang, ctype in m.captions.items():
            assert ctype in ('auto', 'manual'), f'Unexpected caption type {ctype!r} in {f}'
        print(f'OK: {f}')
    except Exception as e:
        fails.append((f, e))
        print(f'FAIL: {f} → {e}')
sys.exit(1 if fails else 0)
PY
```

**Fail path:** If any cache file fails, stop and investigate. Options: (a) relax the model (e.g., expand `Literal` union), (b) write a one-shot cache migration, or (c) delete the offending cache entry if it is unreachable / corrupt. Do not proceed with PR-B until all pass.

## Test Strategy

### PR-A tests
- Valid `Meta` construction with all 9 fields succeeds.
- Missing any required field → `ValidationError`.
- `duration=-1` → `ValidationError`.
- `captions={'en': 'auto'}` valid; `captions={'en': 'autop'}` → `ValidationError`.
- `last_used_at='yesterday'` → `ValidationError`; `last_used_at='2026-04-16T15:13:50.653895+00:00'` succeeds and is stored as `datetime`.
- `description` omitted → defaults to `''`.

### PR-B tests
- Corruption-rejection: pre-populate a temp `meta.json` with an invalid `caption` type; `yttoc_list` / `generate_toc` / etc. raise `ValidationError` on read. One representative test is enough; each site uses the same `Meta.model_validate_json` call.
- `_update_last_used` round-trip: call it twice, read back via `Meta.model_validate_json`, assert `last_used_at` is a `datetime` instance and is monotonically non-decreasing between calls.
- Existing tests continue to pass with the 8 fixture cells updated to the full 9-field Meta shape.

## Non-Goals

- `upload_date` format validation (YYYYMMDD regex) — YAGNI; yt-dlp guarantees the format.
- Schema versioning in `meta.json` — YAGNI for pre-alpha.
- Migration of `video` block in `summaries.json` — Phase 2d.
- Renaming `webpage_url` to `url` anywhere in the pipeline to match summaries.json's `video.url` — that's a deliberate rename inside `_assemble_summaries` and stays as-is until Phase 2d rationalizes it.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Existing `meta.json` caches contain caption values outside `{"auto","manual"}` | Pre-flight script. If any fail, expand the Literal union or add a migration step. |
| `datetime` ISO format mismatch on round-trip (`+00:00` vs `Z` vs microseconds) | Pre-flight verifies current caches parse. Post-migration, write format is fixed to Pydantic v2 default. If we need byte-for-byte match with existing writes, add a `field_serializer` on `last_used_at`. |
| Test fixtures in `nbs/03_toc.ipynb` and `nbs/04_summarize.ipynb` previously omitted `captions` (relying on `.get('captions', {})` in consumer) — now Meta.model_validate_json rejects that | Audit each fixture before PR-B; add `"captions": {"en": "auto"}` where missing. |
| `_assemble_summaries` builds `'video'` dict with a subset of Meta fields and a rename (`webpage_url` → `url`); signature change to `meta: Meta` is clean, output stays dict | Explicit scope boundary; Phase 2d will type the output. |
| Cross-cell import ordering: `Meta` references `datetime` and `Literal` in cell `ec3460e1` of `nbs/00_core.ipynb` | Add imports in the same cell immediately after existing `from pydantic import BaseModel, Field`. |

## Acceptance Criteria

### PR-A
- [ ] `Meta` model defined in `nbs/00_core.ipynb`; exports from `yttoc.core`
- [ ] `from yttoc.core import Meta` works
- [ ] `_build_meta` constructs `Meta` internally and returns `meta.model_dump(mode='json')`
- [ ] `_build_meta` public return shape unchanged (`dict`); existing fetch.py tests pass
- [ ] 4 validation tests pass (invalid captions value, invalid last_used_at, negative duration, missing field)
- [ ] Full `nbdev-test` green

### PR-B
- [ ] Pre-flight confirms all existing cached `meta.json` files validate against `Meta`
- [ ] `_build_meta` returns `Meta` (no model_dump)
- [ ] `fetch_video` writes via `meta.model_dump_json(indent=2)`
- [ ] `_update_last_used` uses Meta for round-trip
- [ ] All 7 meta.json read sites use `Meta.model_validate_json`
- [ ] `format_header`, `_build_toc_prompt`, `_build_summary_prompt`, `_assemble_summaries`, `_load_segments` all take `meta: Meta`
- [ ] Consumer sites use attribute access; no remaining `meta.get(...)` / `meta['...']` on Meta-typed values
- [ ] 8 test fixtures updated to the full 9-field shape
- [ ] Corruption-rejection test and `_update_last_used` round-trip test added and passing
- [ ] Full `nbdev-test` green
- [ ] No `meta\[('|\")(id|title|channel|duration|upload_date|webpage_url|description|captions|last_used_at)(\1)\]` or equivalent `.get(...)` patterns remain on Meta-typed values in fetch, core, xscript, toc, summarize (verify via grep)

## Follow-up work (separate specs)

- `2026-MM-DD-pydantic-phase2d-assembled-summaries-design.md` — Phase 2d. Will define `AssembledSummaries` with typed `video` sub-model (mirroring a subset of `Meta`), typed `AssembledSection` (subclassing `NormalizedSection`), unify `format_toc_line` and `_print_section_summary` consumers, and bring `yttoc/map.py` and `ask._find_section` into the Pydantic world.
