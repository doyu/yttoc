# Pydantic Phase 2d — AssembledSummaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Phase 2 Pydantic migration by typing `summaries.json` (AssembledSummaries envelope with AssembledSection and VideoBlock), finishing the deferred type-purity cleanups for `format_toc_line` and `format_header`, typing `map.py` via `FlattenedSection`, and removing the now-unreachable `_migrate_old_summaries` legacy path.

**Architecture:** Three-PR split, each under the 200-line AGENTS.md soft limit. PR-A introduces new models and uses them internally, preserving the public `dict` API. PR-B flips return types, wraps all 3 `summaries.json` reads with `AssembledSummaries.model_validate_json`, propagates attribute access through `summarize` and `ask`, and deletes `_migrate_old_summaries` + its test cell `11e566da`. PR-C types `map.py` via `FlattenedSection(AssembledSection)` and removes the `| dict` shim from `format_header` and the dict-typed signature on `format_toc_line`.

**Tech Stack:** Python, nbdev 3, Pydantic v2. All `nbdev-*` commands run from `/home/doyu/yttoc/` under `.venv`.

**Spec:** `docs/superpowers/specs/2026-04-19-pydantic-phase2d-assembled-summaries-design.md` (commit `add3b7c`).

**Execution environment:** Use `/home/doyu/yttoc/.venv/bin/python`, `/home/doyu/yttoc/.venv/bin/nbdev-export`, `/home/doyu/yttoc/.venv/bin/nbdev-test`. Edit notebooks by loading JSON with Python, mutating target cells' `source`, writing back, then running `scripts/normalize_notebooks.py`.

**AGENTS.md compliance checkpoints:**
- Stage for review before every commit.
- No direct push to `main`; each PR lives on a feature branch.
- After each merge: resync via `git checkout main && git fetch origin && git reset --hard origin/main`.

---

## File Structure

### PR-A touches
- `nbs/04_summarize.ipynb` — add `VideoBlock`, `AssembledSection`, `AssembledSummaries` models; validation test; `_assemble_summaries` uses models internally
- Generated `yttoc/summarize.py`, `yttoc/_modidx.py`

### PR-B touches
- `nbs/04_summarize.ipynb` — flip return types, remove `_migrate_old_summaries`, remove Test 7, update `_print_section_summary` / `yttoc_sum` / `get_summaries`, expand tests
- `nbs/06_ask.ipynb` — update `_find_section` / `format_citations`
- Generated `yttoc/summarize.py`, `yttoc/ask.py`, `yttoc/_modidx.py`

### PR-C touches
- `nbs/05_map.ipynb` — `FlattenedSection(AssembledSection)` + 5 function updates
- `nbs/00_core.ipynb` — retype `format_header` and `format_toc_line`
- `nbs/03_toc.ipynb` — drop `.model_dump()` adapter in `yttoc_toc`
- Generated `yttoc/core.py`, `yttoc/toc.py`, `yttoc/map.py`, `yttoc/_modidx.py`

---

## PR-A — Introduce `AssembledSummaries` (API-preserving, ~60 lines)

### Task 1: Create PR-A feature branch

**Files:** none

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: clean, up-to-date.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2d-models
```

---

### Task 2: Add `VideoBlock`, `AssembledSection`, `AssembledSummaries` models to `nbs/04_summarize.ipynb`

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cell `404ff620` (contains existing `Evidence`, `SectionSummaryPayload`, `SummaryLLMResult`, `_call_summary_llm`); insert new validation test cell after cell `c1000009` (Test 3 — `_build_summary_prompt`)

- [ ] **Step 1: Inspect cell `404ff620`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/04_summarize.ipynb'))
for c in nb['cells']:
    if c.get('id') == '404ff620':
        print(''.join(c['source']))
"
```

Expected: starts with `#| export`, defines `Evidence`, `SectionSummaryPayload`, `SummaryLLMResult`, then `_call_summary_llm`. Already imports `BaseModel, Field` via cell `c1000004`.

- [ ] **Step 2: Edit cell `404ff620` — add new models**

Insert three new classes immediately after `SummaryLLMResult` and before `_call_summary_llm`. The imports cell `c1000005` already has `NormalizedSection`; we use it here:

First update cell `c1000004` (imports) to also add `NormalizedSection`:

```python
#| export
import json
from pathlib import Path
from pydantic import BaseModel, Field
from yttoc.core import NormalizedSection
```

Then in cell `404ff620`, after the `SummaryLLMResult` class and before `def _call_summary_llm`, insert:

```python
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

Leave `Evidence`, `SectionSummaryPayload`, `SummaryLLMResult`, `_call_summary_llm` unchanged.

- [ ] **Step 3: Insert new validation test cell after cell `c1000009`**

Via Python JSON mutation, insert a new code cell (fresh 8-char hex `id`) after cell with `id == 'c1000009'`. Source:

```python
# Test: VideoBlock, AssembledSection, AssembledSummaries validate required fields and inheritance
from yttoc.summarize import VideoBlock, AssembledSection, AssembledSummaries
from yttoc.core import NormalizedSection
from pydantic import ValidationError

# VideoBlock valid
vb = VideoBlock(id='x', title='t', channel='c', url='u', duration=60, upload_date='20260101')
assert vb.id == 'x' and vb.duration == 60

# VideoBlock rejects missing required field
try:
    VideoBlock(id='x', title='t', channel='c', url='u', duration=60)
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing upload_date'

# AssembledSection inherits NormalizedSection
assert issubclass(AssembledSection, NormalizedSection)
as_ = AssembledSection(path='1', title='Intro', start=0, end=300,
                       summary='s', keywords=['k'],
                       evidence={'text': 'e', 'at': 0})
assert isinstance(as_, NormalizedSection)
assert as_.path == '1' and as_.summary == 's' and as_.evidence.at == 0

# AssembledSection rejects missing summary
try:
    AssembledSection(path='1', title='t', start=0, end=10,
                     keywords=[], evidence={'text': '', 'at': 0})
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing summary'

# AssembledSummaries envelope validates via model_validate_json
doc = '''{"video": {"id": "X", "title": "T", "channel": "C", "url": "u", "duration": 60, "upload_date": "20260101"},
          "sections": [{"path": "1", "title": "I", "start": 0, "end": 30, "summary": "s", "keywords": ["k"], "evidence": {"text": "e", "at": 0}}],
          "full": {"summary": "f", "keywords": ["fk"], "evidence": {"text": "fe", "at": 0}}}'''
doc_model = AssembledSummaries.model_validate_json(doc)
assert doc_model.video.id == 'X'
assert len(doc_model.sections) == 1
assert doc_model.sections[0].title == 'I'

# AssembledSummaries rejects missing top-level envelope key
try:
    AssembledSummaries.model_validate_json('{"sections": [], "full": {"summary": "s", "keywords": [], "evidence": {"text": "", "at": 0}}}')
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing video key'

print('ok')
```

- [ ] **Step 4: Normalize + export + test**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb && .venv/bin/nbdev-export && .venv/bin/nbdev-test --path nbs/04_summarize.ipynb
```

Expected: `Success.`.

---

### Task 3: `_assemble_summaries` uses `AssembledSummaries` internally

**Files:** `nbs/04_summarize.ipynb` cell `d286018a`.

- [ ] **Step 1: Edit `_assemble_summaries` body**

Replace the entire function body with:

```python
def _assemble_summaries(meta: Meta, # Parsed Meta instance
                        toc_sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                        llm_result: dict # {full, sections: {path: {...}}}
                       ) -> dict: # Self-contained summaries.json payload
    "Merge meta + toc + LLM output into the canonical summaries.json shape. Raise if LLM omitted any section."
    missing = [sec.path for sec in toc_sections if sec.path not in llm_result['sections']]
    if missing:
        raise ValueError(f"LLM omitted summaries for sections: {missing}")
    result = AssembledSummaries(
        video=VideoBlock(
            id=meta.id,
            title=meta.title,
            channel=meta.channel,
            url=meta.webpage_url,
            duration=meta.duration,
            upload_date=meta.upload_date,
        ),
        sections=[
            AssembledSection(**sec.model_dump(), **llm_result['sections'][sec.path])
            for sec in toc_sections
        ],
        full=llm_result['full'],
    )
    return result.model_dump(mode='json')
```

Key changes:
- Dict-literal return replaced with `AssembledSummaries(video=..., sections=..., full=...)` construction
- Nested `VideoBlock(...)` for the video sub-block (replaces the nested dict)
- Sections list built via `AssembledSection(**sec.model_dump(), **llm_result['sections'][sec.path])` (spread merges NormalizedSection + LLM payload fields)
- `full=llm_result['full']` — Pydantic coerces the dict into `SectionSummaryPayload` automatically
- Final `return result.model_dump(mode='json')` preserves the public `list[dict]` contract (no consumer impact in PR-A)

Also import `VideoBlock, AssembledSection, AssembledSummaries` in the cell. The cell already imports from `yttoc.core` and `yttoc.fetch` etc., but not from summarize's own class definitions since those are in the same module file. Actually the classes live in the same `yttoc.summarize` module — no import needed within the same cell's module scope.

Leave `_migrate_old_summaries`, `generate_summaries`, `_print_section_summary`, `yttoc_sum` unchanged.

- [ ] **Step 2: Normalize + export + full tests**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb && .venv/bin/nbdev-export && .venv/bin/nbdev-test
```

Expected: `Success.`. Public API unchanged (`_assemble_summaries` returns `dict`), so all existing tests pass.

- [ ] **Step 3: Python-level sanity check**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
from datetime import datetime, timezone
from yttoc.core import Meta, NormalizedSection
from yttoc.summarize import _assemble_summaries
meta = Meta(id='X', title='T', channel='C', duration=600, upload_date='20260101',
            webpage_url='https://y.com/X', description='', captions={'en': 'auto'},
            last_used_at=datetime.now(timezone.utc))
sections = [NormalizedSection(path='1', title='Intro', start=0, end=300)]
llm = {'full': {'summary': 'f', 'keywords': ['fk'], 'evidence': {'text': 'fe', 'at': 0}},
       'sections': {'1': {'summary': 's', 'keywords': ['k'], 'evidence': {'text': 'e', 'at': 0}}}}
result = _assemble_summaries(meta, sections, llm)
assert isinstance(result, dict)
assert result['video']['id'] == 'X'
assert result['video']['url'] == 'https://y.com/X'
assert result['sections'][0]['summary'] == 's'
assert result['full']['summary'] == 'f'
print('OK')
"
```

Expected: `OK`.

---

### Task 4: Stage, commit, push, open PR-A

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/04_summarize.ipynb yttoc/summarize.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff**

```bash
git status && git diff --cached --stat && git diff --cached
```

Expected: 3 files changed. `yttoc/summarize.py` adds `VideoBlock`, `AssembledSection`, `AssembledSummaries` classes and updates `_assemble_summaries` to construct them.

- [ ] **Step 3: Pause for user review**

Ask: "PR-A staged diff ready. Approve to commit?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(summarize): introduce VideoBlock, AssembledSection, AssembledSummaries (PR-A)

Phase 2d PR-A — adds three Pydantic models to yttoc.summarize:
- VideoBlock: 6-field video header (id, title, channel, url, duration,
  upload_date) persisted inside summaries.json. Kept distinct from Meta
  because summaries.json uses 'url' (not 'webpage_url') and excludes
  description/captions/last_used_at.
- AssembledSection(NormalizedSection): inherits the 4 TOC-section
  fields and adds summary/keywords/evidence. Enables format_toc_line
  polymorphism in PR-C.
- AssembledSummaries: envelope with video, sections, full (reuses the
  Phase 1 SectionSummaryPayload type).

_assemble_summaries constructs AssembledSummaries internally and
returns meta.model_dump(mode='json') so the public dict API is
preserved. Zero consumer impact in PR-A.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2d-models
gh pr create --title "refactor(summarize): introduce VideoBlock, AssembledSection, AssembledSummaries (Phase 2d PR-A)" --body "$(cat <<'EOF'
## Summary

Phase 2d PR-A (of 3) — adds Pydantic models for \`summaries.json\`. Public API unchanged: \`_assemble_summaries\` still returns a dict (via \`.model_dump(mode='json')\`). PR-B will flip the return type and add strict on-read validation; PR-C will type \`map.py\` and finalize \`format_header\` / \`format_toc_line\` purity.

## Models

- \`VideoBlock\` — 6-field video header persisted inside summaries.json
- \`AssembledSection(NormalizedSection)\` — inherits the 4 TOC-section fields, adds summary/keywords/evidence
- \`AssembledSummaries\` — envelope with \`video: VideoBlock\`, \`sections: list[AssembledSection]\`, \`full: SectionSummaryPayload\` (Phase 1 type reused)

## Placement

All three models in \`yttoc.summarize\` next to \`_assemble_summaries\` and \`SectionSummaryPayload\` (file-envelope pattern, matches \`TocFile\` in \`yttoc.toc\`). \`AssembledSection\` inherits \`NormalizedSection\` (in \`yttoc.core\`) so \`format_toc_line\` can accept both via polymorphism (materialized in PR-C).

See spec \`docs/superpowers/specs/2026-04-19-pydantic-phase2d-assembled-summaries-design.md\`.

## Test plan

- [x] \`nbdev-test\` full suite passes (public contract unchanged)
- [x] New test validates all three models including the \`AssembledSection isinstance NormalizedSection\` invariant
- [x] \`AssembledSummaries.model_validate_json\` rejects missing envelope keys

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI + user merge**

Stop here. Do NOT proceed to PR-B until user merges and local main is resynced.

- [ ] **Step 7: After merge, resync local main**

```bash
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2d-models 2>/dev/null || true && git log --oneline -3
```

---

## PR-B — Propagate through `summarize` + `ask`; strict on-read validation (~150 lines)

**⚠ Atomic refactor note:** PR-B flips public return types. Between Task 7 and Task 11, tests are red mid-refactor. Only run full `nbdev-test` at Task 12. Targeted per-notebook tests are acceptable for sanity checks.

### Task 5: Pre-flight — verify cached `summaries.json` files validate

**Files:** none (verification).

- [ ] **Step 1: Run pre-flight script**

```bash
/home/doyu/yttoc/.venv/bin/python <<'PYEOF'
from pathlib import Path
from yttoc.summarize import AssembledSummaries
import sys
fails = []
cache_root = Path.home() / '.cache' / 'yttoc'
if not cache_root.exists():
    print('No cache root; skipping.')
    sys.exit(0)
for f in sorted(cache_root.glob('*/summaries.json')):
    try:
        AssembledSummaries.model_validate_json(f.read_text(encoding='utf-8'))
        print(f'OK: {f}')
    except Exception as e:
        fails.append((f, e))
        print(f'FAIL: {f} -> {e}')
print(f'\n{len(fails)} failures')
sys.exit(1 if fails else 0)
PYEOF
```

Expected: every `summaries.json` prints `OK:`. If any fail, STOP and escalate. Do not branch yet.

---

### Task 6: Create PR-B feature branch

- [ ] **Step 1: Verify clean main and PR-A merged**

```bash
cd /home/doyu/yttoc && git checkout main && git status && git log -1 --oneline
```

Expected: clean, last commit is the PR-A merge.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2d-propagate
```

---

### Task 7: Flip `_assemble_summaries` + `generate_summaries` return types; delete `_migrate_old_summaries`

**Files:** `nbs/04_summarize.ipynb` cell `d286018a`.

- [ ] **Step 1: Edit `_assemble_summaries` return type**

Change the annotation and drop `.model_dump(mode='json')`:

Before (from PR-A):
```python
def _assemble_summaries(meta: Meta,
                        toc_sections: list[NormalizedSection],
                        llm_result: dict
                       ) -> dict: # Self-contained summaries.json payload
    ...
    result = AssembledSummaries(...)
    return result.model_dump(mode='json')
```

After:
```python
def _assemble_summaries(meta: Meta,
                        toc_sections: list[NormalizedSection],
                        llm_result: dict
                       ) -> AssembledSummaries: # Parsed AssembledSummaries instance
    ...
    return AssembledSummaries(
        video=VideoBlock(
            id=meta.id,
            title=meta.title,
            channel=meta.channel,
            url=meta.webpage_url,
            duration=meta.duration,
            upload_date=meta.upload_date,
        ),
        sections=[
            AssembledSection(**sec.model_dump(), **llm_result['sections'][sec.path])
            for sec in toc_sections
        ],
        full=llm_result['full'],
    )
```

Two edits: return annotation `dict → AssembledSummaries`, drop the `result = ...; return result.model_dump(mode='json')` two-line pattern and return the `AssembledSummaries(...)` construction directly.

- [ ] **Step 2: Delete `_migrate_old_summaries`**

Remove the entire `_migrate_old_summaries` function definition (starts with `def _migrate_old_summaries(cached: dict, ...`). Nothing else in the cell references it after Step 3's `generate_summaries` update.

- [ ] **Step 3: Edit `generate_summaries` — remove legacy branch, use AssembledSummaries for I/O**

Replace the entire function body with:

```python
def generate_summaries(video_id: str, # Exact video_id
                       root: Path = None, # Root cache directory
                       refresh: bool = False, # Delete cached summaries and regenerate
                      ) -> AssembledSummaries: # Parsed AssembledSummaries instance
    "Generate summaries.json for a cached video. Returns parsed AssembledSummaries."
    root = root or _DEFAULT_ROOT
    d = root / video_id
    meta_path = d / 'meta.json'
    sum_path = d / 'summaries.json'
    srt_files = _glob_srt(d)
    if not (meta_path.exists() and srt_files):
        raise SystemExit(f"Not cached: {video_id}")

    if refresh and sum_path.exists():
        sum_path.unlink()

    if sum_path.exists():
        return AssembledSummaries.model_validate_json(sum_path.read_text(encoding='utf-8'))

    toc_sections = generate_toc(video_id, root)
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_summary_prompt(segments, toc_sections, meta)
    llm_result = _call_summary_llm(prompt)
    result = _assemble_summaries(meta, toc_sections, llm_result)

    sum_path.write_text(result.model_dump_json(indent=2), encoding='utf-8')
    _update_last_used(meta_path)
    return result
```

Key changes:
- Return annotation `dict → AssembledSummaries`
- Cache-hit branch uses `AssembledSummaries.model_validate_json(...)` (no more legacy detection)
- Write uses `result.model_dump_json(indent=2)` (no more `json.dumps`)
- `_migrate_old_summaries` call is gone

- [ ] **Step 4: Normalize (do not run full tests yet)**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 8: Delete legacy migration test cell `11e566da`

**Files:** `nbs/04_summarize.ipynb` — remove cell `11e566da`.

- [ ] **Step 1: Remove the cell**

Via Python JSON mutation: load notebook, filter out the cell with `id == '11e566da'`, write back:

```bash
/home/doyu/yttoc/.venv/bin/python <<'PYEOF'
import json
path = '/home/doyu/yttoc/nbs/04_summarize.ipynb'
nb = json.load(open(path))
before = len(nb['cells'])
nb['cells'] = [c for c in nb['cells'] if c.get('id') != '11e566da']
after = len(nb['cells'])
assert after == before - 1, f'expected to remove 1 cell; removed {before - after}'
with open(path, 'w') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
    f.write('\n')
print(f'removed 1 cell; {after} remain')
PYEOF
```

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 9: Update `get_summaries` to return `AssembledSummaries | dict`

**Files:** `nbs/04_summarize.ipynb` cell `73e522f6`.

- [ ] **Step 1: Edit `get_summaries`**

Replace:
```python
def get_summaries(video_id: str, # Exact video_id
                  root: Path = None # Root cache directory (default: ~/.cache/yttoc)
                 ) -> dict: # summaries.json content verbatim, or {"error": "..."}
    "Return summaries.json for a cached video. No transformation — file content returned as-is."
    root = root or _DEFAULT_ROOT
    sum_path = root / video_id / 'summaries.json'
    if not sum_path.exists():
        return {'error': f'summaries.json not found for {video_id}'}
    return json.loads(sum_path.read_text(encoding='utf-8'))
```

With:
```python
def get_summaries(video_id: str, # Exact video_id
                  root: Path = None # Root cache directory (default: ~/.cache/yttoc)
                 ) -> AssembledSummaries | dict: # Parsed AssembledSummaries or {"error": "..."}
    "Return summaries.json for a cached video. Validates via AssembledSummaries; error branch returns {'error': ...}."
    root = root or _DEFAULT_ROOT
    sum_path = root / video_id / 'summaries.json'
    if not sum_path.exists():
        return {'error': f'summaries.json not found for {video_id}'}
    return AssembledSummaries.model_validate_json(sum_path.read_text(encoding='utf-8'))
```

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 10: Update `_print_section_summary` and `yttoc_sum`

**Files:** `nbs/04_summarize.ipynb` cell `d286018a`.

- [ ] **Step 1: Edit `_print_section_summary`**

Before:
```python
def _print_section_summary(s: dict, url: str):
    "Render one section as a TOC-style header followed by summary/keywords/evidence."
    print(f"## {format_toc_line(s, url)}")
    print(s['summary'])
    print(f"**Keywords:** {', '.join(s['keywords'])}")
    print(f"**Evidence:** \"{s['evidence']['text']}\" [{fmt_duration(s['evidence']['at'])}]")
```

After:
```python
def _print_section_summary(s: AssembledSection, url: str):
    "Render one section as a TOC-style header followed by summary/keywords/evidence."
    print(f"## {format_toc_line(s, url)}")
    print(s.summary)
    print(f"**Keywords:** {', '.join(s.keywords)}")
    print(f"**Evidence:** \"{s.evidence.text}\" [{fmt_duration(s.evidence.at)}]")
```

Note: `format_toc_line(s, url)` — `s` is now `AssembledSection`. At this point `format_toc_line` still takes a dict (PR-C will retype it). So we need a shim — pass `s.model_dump()`:

```python
    print(f"## {format_toc_line(s.model_dump(), url)}")
```

This is temporary until PR-C. Document the adapter with a brief inline comment:

```python
    # format_toc_line still dict-typed until Phase 2d PR-C; adapt here
    print(f"## {format_toc_line(s.model_dump(), url)}")
```

- [ ] **Step 2: Edit `yttoc_sum`**

Before:
```python
@call_parse
def yttoc_sum(video_id: str, # Exact video_id
              section: str = '', # Section path (e.g. "3"); empty for all
              root: str = None, # Root cache directory
              refresh: bool = False, # Regenerate summaries
             ):
    "Display summaries for a cached video."
    root = Path(root) if root else _DEFAULT_ROOT
    sums = generate_summaries(video_id, root, refresh=refresh)
    video = sums['video']
    url = video.get('url') or ''

    print(format_header(video))
    print()

    if section:
        s = next((sec for sec in sums['sections'] if sec['path'] == section), None)
        if s is None:
            raise SystemExit(f"Section {section} not found")
        _print_section_summary(s, url)
    else:
        for s in sums['sections']:
            _print_section_summary(s, url)
            print()

        print("## Full Summary")
        print(sums['full']['summary'])
        print(f"**Keywords:** {', '.join(sums['full']['keywords'])}")
        print(f"**Evidence:** \"{sums['full']['evidence']['text']}\" [{fmt_duration(sums['full']['evidence']['at'])}]")
        if url: print(url)
```

After:
```python
@call_parse
def yttoc_sum(video_id: str, # Exact video_id
              section: str = '', # Section path (e.g. "3"); empty for all
              root: str = None, # Root cache directory
              refresh: bool = False, # Regenerate summaries
             ):
    "Display summaries for a cached video."
    root = Path(root) if root else _DEFAULT_ROOT
    sums = generate_summaries(video_id, root, refresh=refresh)
    url = sums.video.url or ''

    print(format_header(sums.video))
    print()

    if section:
        s = next((sec for sec in sums.sections if sec.path == section), None)
        if s is None:
            raise SystemExit(f"Section {section} not found")
        _print_section_summary(s, url)
    else:
        for s in sums.sections:
            _print_section_summary(s, url)
            print()

        print("## Full Summary")
        print(sums.full.summary)
        print(f"**Keywords:** {', '.join(sums.full.keywords)}")
        print(f"**Evidence:** \"{sums.full.evidence.text}\" [{fmt_duration(sums.full.evidence.at)}]")
        if url: print(url)
```

Note: `format_header(sums.video)` now passes `VideoBlock`. `format_header` in Phase 2c accepts `Meta | dict`. After PR-B we need it to accept `VideoBlock` as well. Temporarily, pass a dict via `sums.video.model_dump()` for compatibility:

```python
    print(format_header(sums.video.model_dump()))
```

This is a temporary adapter until PR-C retypes `format_header(meta: Meta | VideoBlock)`. Add a short inline comment:

```python
    # format_header accepts Meta | dict until Phase 2d PR-C; adapt VideoBlock here
    print(format_header(sums.video.model_dump()))
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 11: Update `ask.py` — `_find_section` and `format_citations`

**Files:** `nbs/06_ask.ipynb` cell `d2cf5745`.

- [ ] **Step 1: Edit the cell**

Find `_find_section` and `format_citations`. Replace with:

```python
from yttoc.summarize import get_summaries as _read_summaries, AssembledSection
from yttoc.xscript import get_xscript_range as _read_xscript_range
from yttoc.core import fmt_duration

def _find_section(sections: list[AssembledSection], seconds: int) -> AssembledSection | None:
    "Find the section containing the given timestamp. Returns None if no match."
    for s in sections:
        if s.start <= seconds < s.end:
            return s
    return None

def format_citations(citations: list[Citation], # List of Citation objects
                     root: Path = None # Cache root for summaries lookup
                    ) -> list[str]: # Formatted citation lines
    "Resolve Citation objects into display lines with YouTube deep links."
    from yttoc.fetch import _DEFAULT_ROOT
    root = root or _DEFAULT_ROOT
    lines = []
    for i, c in enumerate(citations, 1):
        vid, sec = c.video_id, c.seconds
        url = f'https://youtu.be/{vid}?t={sec}'
        ts = fmt_duration(sec)
        sums = _read_summaries(vid, root)
        if isinstance(sums, dict):  # error branch: {'error': '...'}
            lines.append(f'  [{i}] {vid} @ {ts}\n      {url}')
            continue
        title = sums.video.title
        section = _find_section(sums.sections, sec)
        if section:
            lines.append(f'  [{i}] {title} \u00a7{section.path} "{section.title}" @ {ts}\n      {url}')
        else:
            lines.append(f'  [{i}] {title} @ {ts}\n      {url}')
    return lines
```

Key changes:
- `from yttoc.summarize import ... AssembledSection` added to imports
- `_find_section` signature and body use `AssembledSection` / attribute access
- `format_citations` — `sums` is now `AssembledSummaries | dict`. `if isinstance(sums, dict)` replaces `if 'error' in sums`. Attribute access on `sums.video.title` and `sums.sections` and `section.path` / `section.title`

Leave `build_registry` (the remainder of the cell) unchanged.

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/06_ask.ipynb
```

---

### Task 12: Update tests 4/5/6/9 to use attribute access on `generate_summaries` / `get_summaries` return

**Files:** `nbs/04_summarize.ipynb` cells `aa6db3d2`, `87bf3d0d`, `fbf6535c`, `a37b70d6`.

After PR-B, `generate_summaries` returns `AssembledSummaries` and `get_summaries` returns `AssembledSummaries | dict`. Tests that assert on the return value's shape need attribute access.

- [ ] **Step 1: Inspect each test cell**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/04_summarize.ipynb'))
for c in nb['cells']:
    if c.get('id') in ('aa6db3d2','87bf3d0d','fbf6535c','a37b70d6'):
        print(f'=== {c[\"id\"]} ===')
        print(''.join(c['source']))
        print()
"
```

- [ ] **Step 2: Update cell `aa6db3d2` (Test 4) — attribute-access assertions on `generate_summaries` return**

The cell pre-writes a summaries.json fixture (dict form — stays dict since it represents on-disk JSON), then calls `generate_summaries` and asserts. Find the assertions after `result = generate_summaries('VID1', root)` and replace:

Before:
```python
    result = generate_summaries('VID1', root)
    assert result['video']['id'] == 'VID1'
    assert isinstance(result['sections'], list)
    assert len(result['sections']) == 2
    assert result['sections'][0]['title'] == 'Intro'
    assert result['full']['summary'] == 'Full video about testing.'
```

(If the exact assertion text differs from the above, preserve intent: rewrite `result['X']['Y']` dict subscripts to `result.X.Y` attribute access.)

After:
```python
    result = generate_summaries('VID1', root)
    assert result.video.id == 'VID1'
    assert isinstance(result.sections, list)
    assert len(result.sections) == 2
    assert result.sections[0].title == 'Intro'
    assert result.full.summary == 'Full video about testing.'
```

- [ ] **Step 3: Cell `87bf3d0d` (Test 5) — `yttoc_sum` stdout-only assertions**

Test 5 asserts on stdout strings only (no subscript access on Python return values). No change needed. Verify:

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/04_summarize.ipynb'))
for c in nb['cells']:
    if c.get('id') == '87bf3d0d':
        src = ''.join(c['source'])
        # Count subscript accesses on result/sums value
        import re
        hits = re.findall(r'(result|sums)\[', src)
        print(f'subscripts: {len(hits)}')
"
```

Expected: `subscripts: 0`. If non-zero, update per Step 2's pattern.

- [ ] **Step 4: Cell `fbf6535c` (Test 6) — same, stdout-only**

Same inspection and update as Step 3.

- [ ] **Step 5: Cell `a37b70d6` (Test 9) — `get_summaries` returns AssembledSummaries**

Before:
```python
    result = get_summaries('VID_GS', root)
    assert result == fixture, 'must return file verbatim'
    assert 'full' in result, 'must include full field'
```

After:
```python
    result = get_summaries('VID_GS', root)
    from yttoc.summarize import AssembledSummaries
    assert isinstance(result, AssembledSummaries)
    assert result.video.id == 'VID_GS'
    assert result.sections[0].title == 'Intro'
    assert result.full.summary == 'full'
```

The "verbatim" assertion is replaced by structural equivalence checks because `get_summaries` now parses and returns a model, not a raw dict.

- [ ] **Step 6: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 13: Add corruption-rejection + round-trip tests

**Files:** `nbs/04_summarize.ipynb` — insert two new code cells after cell `a37b70d6` (current last non-CLI test in summarize notebook) or after `766973e1` (Test 10). Either works; use `766973e1`.

- [ ] **Step 1: Insert corruption-rejection test cell**

```python
# Test: get_summaries rejects a corrupted summaries.json (missing evidence field)
from tempfile import TemporaryDirectory
from pydantic import ValidationError

with TemporaryDirectory() as d:
    root = Path(d)
    v = root / 'BAD_SUM'; v.mkdir()
    # Bad shape: section is missing `evidence`
    (v / 'summaries.json').write_text(json.dumps({
        'video': {'id': 'BAD_SUM', 'title': 'T', 'channel': 'C',
                  'url': '', 'duration': 60, 'upload_date': '20260101'},
        'sections': [
            {'path': '1', 'title': 'I', 'start': 0, 'end': 10,
             'summary': 's', 'keywords': ['k']}  # no 'evidence'
        ],
        'full': {'summary': 'f', 'keywords': ['fk'], 'evidence': {'text': 'fe', 'at': 0}},
    }))

    try:
        get_summaries('BAD_SUM', root)
    except ValidationError:
        pass
    else:
        assert False, 'expected ValidationError for missing evidence field'
print('ok')
```

- [ ] **Step 2: Insert round-trip test cell**

```python
# Test: AssembledSummaries round-trip preserves fields through model_dump_json -> model_validate_json
from yttoc.summarize import AssembledSummaries, VideoBlock, AssembledSection

original = AssembledSummaries(
    video=VideoBlock(id='R', title='T', channel='C', url='u',
                     duration=60, upload_date='20260101'),
    sections=[
        AssembledSection(path='1', title='I', start=0, end=30,
                         summary='s', keywords=['k'],
                         evidence={'text': 'e', 'at': 5}),
    ],
    full={'summary': 'f', 'keywords': ['fk'], 'evidence': {'text': 'fe', 'at': 0}},
)
serialized = original.model_dump_json(indent=2)
reparsed = AssembledSummaries.model_validate_json(serialized)
assert reparsed == original, 'round-trip mismatch'
assert reparsed.sections[0].evidence.at == 5
print('ok')
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 14: Export, full tests, grep verify

- [ ] **Step 1: Export**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-export
```

- [ ] **Step 2: Full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test
```

Expected: `Success.`.

- [ ] **Step 3: Grep — no AssembledSummaries dict-style access remains**

```bash
cd /home/doyu/yttoc && grep -nE "sums?\[('|\")(video|sections|full)(\1)\]" yttoc/summarize.py yttoc/ask.py
```

Expected: no hits.

```bash
cd /home/doyu/yttoc && grep -nE "sec\[('|\")(summary|keywords|evidence)(\1)\]" yttoc/summarize.py yttoc/ask.py yttoc/map.py
```

Expected: hits only in `yttoc/map.py` (map.py is PR-C scope — still dict-based).

- [ ] **Step 4: `nbdev-prepare`**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-prepare
```

Expected: `Success.`.

---

### Task 15: Stage, review, commit, push, open PR-B

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/04_summarize.ipynb nbs/06_ask.ipynb yttoc/summarize.py yttoc/ask.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff**

```bash
git status && git diff --cached --stat && git diff --cached | head -500
```

Expected: 2 notebooks + 3 generated files.

- [ ] **Step 3: Pause for user review**

Ask: "PR-B staged diff ready. Approve to commit?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(summarize,ask): propagate AssembledSummaries (PR-B)

PR-B of Phase 2d — flips _assemble_summaries, generate_summaries,
and get_summaries to return AssembledSummaries. All 3 summaries.json
read sites use AssembledSummaries.model_validate_json.

Key changes:
- _migrate_old_summaries removed (legacy path unreachable; all current
  caches are new shape).
- Legacy-detection branch in generate_summaries removed; Test 7
  (cell 11e566da) deleted.
- _print_section_summary, yttoc_sum, _find_section, format_citations
  all use attribute access on AssembledSummaries / AssembledSection
  / VideoBlock.
- format_toc_line and format_header remain dict-typed; VideoBlock
  and AssembledSection callers temporarily pass .model_dump() until
  PR-C retypes them.
- Tests 4/9 updated to attribute access; Tests 5/6 stdout-only, no
  code change.
- New: corruption-rejection test + AssembledSummaries round-trip test.

Pre-flight: all 17 cached summaries.json files validate against
AssembledSummaries before branch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2d-propagate
gh pr create --title "refactor(summarize,ask): propagate AssembledSummaries (Phase 2d PR-B)" --body "$(cat <<'EOF'
## Summary

Phase 2d PR-B (of 3) — follows PR-A (models). Flips the public types of \`_assemble_summaries\`, \`generate_summaries\`, and \`get_summaries\` to \`AssembledSummaries\`. Wraps every \`summaries.json\` read with \`AssembledSummaries.model_validate_json\`. Removes the unreachable \`_migrate_old_summaries\` legacy path and its test cell.

Two consumer-side temporary adapters remain:
- \`_print_section_summary\` passes \`s.model_dump()\` to \`format_toc_line\` (dict-typed until PR-C)
- \`yttoc_sum\` passes \`sums.video.model_dump()\` to \`format_header\` (accepts \`Meta | dict\` until PR-C)

PR-C removes both adapters when it retypes \`format_toc_line(section: NormalizedSection)\` and \`format_header(meta: Meta | VideoBlock)\`.

## Test plan

- [x] \`nbdev-test\` full suite passes
- [x] Corruption-rejection: missing \`evidence\` field raises \`ValidationError\`
- [x] Round-trip: \`AssembledSummaries.model_dump_json\` → \`model_validate_json\` preserves equality
- [x] Pre-flight: all 17 cached \`summaries.json\` files validate

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI + user merge + resync**

```bash
gh pr checks <PR_NUMBER>
# after merge:
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2d-propagate 2>/dev/null || true
```

---

## PR-C — Type `map.py` + finalize `core.py` purity (~90 lines)

### Task 16: Create PR-C feature branch

- [ ] **Step 1: Verify clean main and PR-B merged**

```bash
cd /home/doyu/yttoc && git checkout main && git status && git log -1 --oneline
```

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2d-finalize
```

---

### Task 17: Add `FlattenedSection` model to `nbs/05_map.ipynb`

**Files:** `nbs/05_map.ipynb` cells `e1000005` (imports) and `e1000006` (utility functions + `load_summaries`, `flatten_sections`).

- [ ] **Step 1: Update imports cell `e1000005`**

Before:
```python
#| export
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
```

After:
```python
#| export
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from pydantic import Field
from yttoc.summarize import AssembledSection, AssembledSummaries
```

- [ ] **Step 2: Insert `FlattenedSection` class in cell `e1000006`**

At the top of cell `e1000006` (right after `#| export` and BEFORE `def _norm_kw`), insert:

```python
class FlattenedSection(AssembledSection):
    "One row of the cross-video keyword/topic grid. Inherits the 7 AssembledSection fields and adds video context."
    lesson: int = Field(ge=1, description="1-based index in the lesson list")
    video_id: str = Field(description="YouTube video ID")
    video_title: str = Field(description="Video title")
    jump_url: str = Field(description="Deep-link URL for the section start")
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/05_map.ipynb
```

---

### Task 18: Retype `load_summaries`, `flatten_sections`, `_section_label`

**Files:** `nbs/05_map.ipynb` cell `e1000006`.

- [ ] **Step 1: Retype `_section_label`**

Before:
```python
def _section_label(row: dict # Flattened section record
                  ) -> str: # 'L{lesson} §{path} {title}'
    "Short human label for a section across the whole course."
    return f"L{row['lesson']} §{row['path']} {row['title']}"
```

After:
```python
def _section_label(row: FlattenedSection # Flattened section record
                  ) -> str: # 'L{lesson} §{path} {title}'
    "Short human label for a section across the whole course."
    return f"L{row.lesson} §{row.path} {row.title}"
```

- [ ] **Step 2: Retype `load_summaries`**

Before:
```python
def load_summaries(video_ids: list[str], # Ordered video ids (lesson 1, 2, ...)
                   root: Path # Cache root dir
                  ) -> list[dict]: # Loaded summaries with '_lesson' attached
    "Load each video's summaries.json and tag with lesson number from list order."
    docs = []
    for i, vid in enumerate(video_ids, 1):
        p = Path(root) / vid / 'summaries.json'
        if not p.exists(): continue
        doc = json.loads(p.read_text(encoding='utf-8'))
        doc['_lesson'] = i
        docs.append(doc)
    return docs
```

After:
```python
def load_summaries(video_ids: list[str], # Ordered video ids (lesson 1, 2, ...)
                   root: Path # Cache root dir
                  ) -> list[tuple[int, AssembledSummaries]]: # Lesson-tagged summaries
    "Load each video's summaries.json and pair with lesson number from list order."
    docs = []
    for i, vid in enumerate(video_ids, 1):
        p = Path(root) / vid / 'summaries.json'
        if not p.exists(): continue
        doc = AssembledSummaries.model_validate_json(p.read_text(encoding='utf-8'))
        docs.append((i, doc))
    return docs
```

Rationale: `AssembledSummaries` rejects extra attributes (Pydantic default), so the previous `doc['_lesson'] = i` monkey-patch no longer works — mirror the `yttoc_list` pattern from Phase 2c: return a `(lesson, summaries)` tuple.

- [ ] **Step 3: Retype `flatten_sections`**

Before:
```python
def flatten_sections(docs: list[dict] # Loaded summaries
                    ) -> list[dict]: # One row per section with video context
    "Flatten all docs into one section-level list with lesson/video metadata attached."
    rows = []
    for doc in docs:
        v = doc['video']
        url = v.get('url') or ''
        for sec in doc['sections']:
            jump = f"{url}&t={sec['start']}" if url else ''
            rows.append({
                'lesson': doc['_lesson'],
                'video_id': v['id'],
                'video_title': v['title'],
                'jump_url': jump,
                **sec,
            })
    return rows
```

After:
```python
def flatten_sections(docs: list[tuple[int, AssembledSummaries]] # Lesson-tagged summaries
                    ) -> list[FlattenedSection]: # One FlattenedSection per section with video context
    "Flatten all docs into one section-level list with lesson/video metadata attached."
    rows = []
    for lesson, doc in docs:
        v = doc.video
        url = v.url or ''
        for sec in doc.sections:
            jump = f"{url}&t={sec.start}" if url else ''
            rows.append(FlattenedSection(
                **sec.model_dump(),
                lesson=lesson,
                video_id=v.id,
                video_title=v.title,
                jump_url=jump,
            ))
    return rows
```

- [ ] **Step 4: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/05_map.ipynb
```

---

### Task 19: Retype `render_by_lecture`, `_build_keyword_index`, `render_by_topic`, `render_by_keyword`

**Files:** `nbs/05_map.ipynb` cell `e1000007`.

- [ ] **Step 1: Inspect the cell**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/05_map.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'e1000007':
        print(''.join(c['source']))
"
```

- [ ] **Step 2: Retype `render_by_lecture`**

Before:
```python
def render_by_lecture(docs: list[dict] # Loaded summaries
                     ) -> str: # Markdown fragment
    "Render the By Lecture view (Lesson → sections in playback order)."
    lines = ['## By Lecture', '']
    for doc in docs:
        v = doc['video']
        url = v.get('url') or ''
        lines.append(f"- Lesson {doc['_lesson']}: {v['title']}")
        for sec in doc['sections']:
            jump = f"{url}&t={sec['start']}" if url else '#'
            lines.append(f"  - [{sec['path']}. {sec['title']}]({jump})")
    return '\n'.join(lines)
```

After:
```python
def render_by_lecture(docs: list[tuple[int, AssembledSummaries]] # Lesson-tagged summaries
                     ) -> str: # Markdown fragment
    "Render the By Lecture view (Lesson → sections in playback order)."
    lines = ['## By Lecture', '']
    for lesson, doc in docs:
        v = doc.video
        url = v.url or ''
        lines.append(f"- Lesson {lesson}: {v.title}")
        for sec in doc.sections:
            jump = f"{url}&t={sec.start}" if url else '#'
            lines.append(f"  - [{sec.path}. {sec.title}]({jump})")
    return '\n'.join(lines)
```

- [ ] **Step 3: Retype `_build_keyword_index`**

Before:
```python
def _build_keyword_index(rows: list[dict] # Flattened section rows
                        ) -> tuple[dict, dict]: # (norm → [(orig, row), ...], norm → set of lesson nums)
    "Group rows by normalized keyword, also tracking distinct lesson coverage."
    idx = defaultdict(list)
    by_lessons = defaultdict(set)
    for row in rows:
        for kw in row['keywords']:
            n = _norm_kw(kw)
            if not n: continue
            idx[n].append((kw, row))
            by_lessons[n].add(row['lesson'])
    return idx, by_lessons
```

After:
```python
def _build_keyword_index(rows: list[FlattenedSection] # Flattened section rows
                        ) -> tuple[dict, dict]: # (norm → [(orig, row), ...], norm → set of lesson nums)
    "Group rows by normalized keyword, also tracking distinct lesson coverage."
    idx = defaultdict(list)
    by_lessons = defaultdict(set)
    for row in rows:
        for kw in row.keywords:
            n = _norm_kw(kw)
            if not n: continue
            idx[n].append((kw, row))
            by_lessons[n].add(row.lesson)
    return idx, by_lessons
```

- [ ] **Step 4: Retype `render_by_topic` and `render_by_keyword`**

Inspect their current bodies (they render Markdown from `idx` output, iterating `(kw, row)` pairs). Replace any `row['jump_url']`, `row['path']`, `row['title']`, etc. accesses with `row.jump_url`, `row.path`, `row.title` attribute access. The function signatures change from `rows: list[dict]` to `rows: list[FlattenedSection]`.

Concretely, the body of `render_by_topic` calls `_section_label(row)`; `_section_label` is already retyped (Task 18). Links produced via `row['jump_url']` become `row.jump_url`.

Apply the same pattern to `render_by_keyword`.

Also update `render_map` if it exists — it orchestrates the three renderers.

- [ ] **Step 5: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/05_map.ipynb
```

---

### Task 20: Migrate `nbs/05_map.ipynb` test fixtures and assertions

**Files:** `nbs/05_map.ipynb` cells `e1000013`, `e1000014`, `e1000015`, `e1000016`, `e1000017`, `e1000018`, `e1000019`.

Test fixtures use a `_make_doc(vid, title, sections)` helper that builds a dict. After Task 18, `load_summaries` returns `list[tuple[int, AssembledSummaries]]`; consumers expect typed inputs.

- [ ] **Step 1: Update `_make_doc` helper (inside cell `e1000013`) to return `AssembledSummaries`**

Before:
```python
def _make_doc(vid, title, sections):
    return {
        'video': {'id': vid, 'title': title, 'channel': 'C',
                  'url': f'https://youtu.be/{vid}', 'duration': 600, 'upload_date': '20260101'},
        'sections': sections,
        'full': {'summary': f'{title} overall.', 'keywords': ['overview'],
                 'evidence': {'text': 'x', 'at': 0}},
    }
```

After:
```python
def _make_doc(vid, title, sections):
    from yttoc.summarize import AssembledSummaries, VideoBlock, AssembledSection
    return AssembledSummaries(
        video=VideoBlock(id=vid, title=title, channel='C',
                         url=f'https://youtu.be/{vid}', duration=600, upload_date='20260101'),
        sections=[AssembledSection(**s) for s in sections],
        full={'summary': f'{title} overall.', 'keywords': ['overview'],
              'evidence': {'text': 'x', 'at': 0}},
    )
```

This helper is used by Tests 3-9 in map. The returned value is now `AssembledSummaries`. Any test that passed it through `load_summaries` implicitly now works because `load_summaries` itself consumes dict (from file) — so fixtures that write the dict to disk then load are still valid. But tests that pass `_make_doc(...)` directly to `flatten_sections` need updating: `flatten_sections` now expects `list[tuple[int, AssembledSummaries]]`, not a bare list.

- [ ] **Step 2: Update Test 4 (cell `e1000014`) — `flatten_sections` input**

Before:
```python
doc = _make_doc('VID', 'Lesson X', [...])
doc['_lesson'] = 1
rows = flatten_sections([doc])
assert ...
assert rows[0]['jump_url'] == 'https://youtu.be/VID&t=0'
assert rows[0]['video_title'] == 'Lesson X'
```

After:
```python
doc = _make_doc('VID', 'Lesson X', [...])
rows = flatten_sections([(1, doc)])
assert len(rows) == 2
assert rows[0].jump_url == 'https://youtu.be/VID&t=0'
assert rows[1].jump_url == 'https://youtu.be/VID&t=137'
assert rows[0].lesson == 1
assert rows[0].video_title == 'Lesson X'
```

- [ ] **Step 3: Update Test 5 (cell `e1000015`) — `render_by_lecture` input**

Before:
```python
docs = [
    {**_make_doc('A', ...), '_lesson': 1},
    {**_make_doc('B', ...), '_lesson': 2},
]
out = render_by_lecture(docs)
```

After:
```python
docs = [
    (1, _make_doc('A', 'Lesson A', [
        AssembledSection(path='1', title='IntroA', start=0, end=100,
                         summary='', keywords=[], evidence={'text': '', 'at': 0})])),
    (2, _make_doc('B', 'Lesson B', [
        AssembledSection(path='1', title='IntroB', start=0, end=100,
                         summary='', keywords=[], evidence={'text': '', 'at': 0}),
        AssembledSection(path='2', title='MainB', start=200, end=400,
                         summary='', keywords=[], evidence={'text': '', 'at': 0})])),
]
out = render_by_lecture(docs)
```

The rest of the test (stdout assertions) stays unchanged.

- [ ] **Step 4: Update Tests 6 and 7 (cells `e1000016`, `e1000017`) — `render_by_topic` / `render_by_keyword`**

These tests build `rows` as a list of dicts directly. Convert to `FlattenedSection(...)` constructors:

Before (Test 6):
```python
rows = [
    {'lesson': 1, 'path': '1', 'title': 'A', 'jump_url': 'u1', 'keywords': ['Git', 'FastHTML', 'unique-to-1']},
    ...
]
```

After:
```python
from yttoc.map import FlattenedSection
from yttoc.summarize import AssembledSection
rows = [
    FlattenedSection(path='1', title='A', start=0, end=10,
                     summary='', keywords=['Git', 'FastHTML', 'unique-to-1'],
                     evidence={'text': '', 'at': 0},
                     lesson=1, video_id='v1', video_title='V1', jump_url='u1'),
    FlattenedSection(path='2', title='B', start=0, end=10,
                     summary='', keywords=['Git'],
                     evidence={'text': '', 'at': 0},
                     lesson=1, video_id='v1', video_title='V1', jump_url='u2'),
    FlattenedSection(path='1', title='C', start=0, end=10,
                     summary='', keywords=['Git', 'fast html'],
                     evidence={'text': '', 'at': 0},
                     lesson=2, video_id='v2', video_title='V2', jump_url='u3'),
]
```

Apply the same pattern to Test 7.

- [ ] **Step 5: Update Test 8 (cell `e1000018`) — `render_map` input**

Same pattern as Test 5: convert `{**_make_doc(...), '_lesson': N}` to `(N, _make_doc(...))`.

- [ ] **Step 6: Update Test 9 (cell `e1000019`) — CLI end-to-end**

This test writes a `summaries.json` file to disk and invokes `yttoc_map` CLI. No change needed — the on-disk format is unchanged; `yttoc_map` internally calls `load_summaries` which validates through `AssembledSummaries.model_validate_json`.

Verify the fixture `_make_doc('A', 'Lesson A', [...]).model_dump(mode='json')` is written as JSON. Before Task 20, the cell wrote `json.dumps(_make_doc(...))` where `_make_doc` returned a dict. After Task 20, `_make_doc` returns `AssembledSummaries`, so replace:

Before:
```python
(root / 'A' / 'summaries.json').write_text(json.dumps(_make_doc('A', 'Lesson A', [...])))
```

After:
```python
(root / 'A' / 'summaries.json').write_text(_make_doc('A', 'Lesson A', [...]).model_dump_json())
```

- [ ] **Step 7: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/05_map.ipynb
```

---

### Task 21: Retype `format_header` and `format_toc_line` in `nbs/00_core.ipynb`

**Files:** `nbs/00_core.ipynb` cell `ec3460e1`.

- [ ] **Step 1: Edit `format_header`**

Before (from Phase 2c):
```python
def format_header(meta: Meta | dict # Parsed Meta instance or summaries.json video dict
                 ) -> str: # Formatted header string
    "Shared header for toc/sum/raw CLI commands."
    if isinstance(meta, dict):
        d = meta
        dur = fmt_duration(d.get('duration', 0))
        return f'# {d.get("title", "")}\nChannel: {d.get("channel", "")} | Duration: {dur} | {d.get("upload_date", "")}'
    dur = fmt_duration(meta.duration)
    return f'# {meta.title}\nChannel: {meta.channel} | Duration: {dur} | {meta.upload_date}'
```

After:
```python
def format_header(meta: "Meta | VideoBlock" # Meta or VideoBlock (both have title/channel/duration/upload_date)
                 ) -> str: # Formatted header string
    "Shared header for toc/sum/raw CLI commands."
    dur = fmt_duration(meta.duration)
    return f'# {meta.title}\nChannel: {meta.channel} | Duration: {dur} | {meta.upload_date}'
```

Note: `VideoBlock` is defined in `yttoc.summarize`; importing it into `yttoc.core` would create a circular dependency (`summarize → core`). The string annotation `"Meta | VideoBlock"` defers evaluation and avoids the cycle. Runtime dispatch works via duck-typed attribute access — both Meta and VideoBlock expose the 4 attributes.

Alternative (if linters complain): keep signature as `meta: Meta` and rely on duck typing (Pydantic v2 models with matching attributes satisfy any attribute-based use). Either works; string annotation is the documentation-friendly choice.

- [ ] **Step 2: Edit `format_toc_line`**

Before:
```python
def format_toc_line(section: dict, # {path, title, start, end}
                    url: str = '' # webpage_url for &t= deep link (omit when empty)
                   ) -> str: # Formatted line
    "Single-line TOC row for a section, optionally with deep-link URL."
    s_start = fmt_duration(section['start'])
    s_end = fmt_duration(section['end'])
    span = fmt_duration(section['end'] - section['start'])
    suffix = f" {url}&t={section['start']}" if url else ''
    return f"{section['path']}. {section['title']} {s_start}-{s_end} ({span}){suffix}"
```

After:
```python
def format_toc_line(section: NormalizedSection, # NormalizedSection or subclass (AssembledSection, FlattenedSection)
                    url: str = '' # webpage_url for &t= deep link (omit when empty)
                   ) -> str: # Formatted line
    "Single-line TOC row for a section, optionally with deep-link URL."
    s_start = fmt_duration(section.start)
    s_end = fmt_duration(section.end)
    span = fmt_duration(section.end - section.start)
    suffix = f" {url}&t={section.start}" if url else ''
    return f"{section.path}. {section.title} {s_start}-{s_end} ({span}){suffix}"
```

Subscript accesses → attribute accesses (5 sites). Subclasses `AssembledSection` and `FlattenedSection` are accepted via polymorphism.

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb
```

---

### Task 22: Drop `.model_dump()` adapters in `yttoc_toc` and `yttoc_sum`

**Files:** `nbs/03_toc.ipynb` cell `795bea0d`; `nbs/04_summarize.ipynb` cell `d286018a`.

- [ ] **Step 1: Edit `yttoc_toc` in `nbs/03_toc.ipynb`**

Find the `yttoc_toc` CLI body loop:
```python
    for s in sections:
        print(format_toc_line(s.model_dump(), url))
```

Replace with:
```python
    for s in sections:
        print(format_toc_line(s, url))
```

(`sections` is `list[NormalizedSection]`; `format_toc_line` now accepts it directly.)

- [ ] **Step 2: Edit `_print_section_summary` and `yttoc_sum` in `nbs/04_summarize.ipynb`**

In `_print_section_summary`, find:
```python
    # format_toc_line still dict-typed until Phase 2d PR-C; adapt here
    print(f"## {format_toc_line(s.model_dump(), url)}")
```

Replace with:
```python
    print(f"## {format_toc_line(s, url)}")
```

In `yttoc_sum`, find:
```python
    # format_header accepts Meta | dict until Phase 2d PR-C; adapt VideoBlock here
    print(format_header(sums.video.model_dump()))
```

Replace with:
```python
    print(format_header(sums.video))
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb nbs/04_summarize.ipynb
```

---

### Task 23: Add polymorphism integration test

**Files:** `nbs/00_core.ipynb` — insert a new test cell after the Meta validation test.

- [ ] **Step 1: Inspect to find the Meta validation test cell id**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/00_core.ipynb'))
for i, c in enumerate(nb['cells']):
    if c.get('cell_type') == 'code':
        src = ''.join(c['source'])
        if 'Meta validates' in src or 'Test: Meta' in src:
            print(f'META_TEST_ID={c.get(\"id\")}  idx={i}')
"
```

Record the id as `<META_TEST_ID>`.

- [ ] **Step 2: Insert polymorphism test cell after `<META_TEST_ID>`**

New code cell source:

```python
# Test: format_toc_line and format_header accept all typed inputs via polymorphism
from datetime import datetime, timezone
from yttoc.core import (Meta, NormalizedSection, format_header, format_toc_line)
from yttoc.summarize import VideoBlock, AssembledSection
from yttoc.map import FlattenedSection

# format_toc_line accepts NormalizedSection, AssembledSection, FlattenedSection
ns = NormalizedSection(path='1', title='Intro', start=0, end=300)
as_ = AssembledSection(path='1', title='Intro', start=0, end=300,
                        summary='s', keywords=['k'],
                        evidence={'text': 'e', 'at': 0})
fs = FlattenedSection(path='1', title='Intro', start=0, end=300,
                      summary='s', keywords=['k'], evidence={'text': 'e', 'at': 0},
                      lesson=1, video_id='X', video_title='V', jump_url='u')

line_ns = format_toc_line(ns, url='https://y.com/X')
line_as = format_toc_line(as_, url='https://y.com/X')
line_fs = format_toc_line(fs, url='https://y.com/X')
# All three produce the same line because only NormalizedSection fields are used
assert line_ns == line_as == line_fs
assert '1. Intro' in line_ns and '&t=0' in line_ns

# format_header accepts Meta and VideoBlock
meta = Meta(id='X', title='T', channel='C', duration=60, upload_date='20260101',
            webpage_url='u', captions={'en': 'auto'},
            last_used_at=datetime.now(timezone.utc))
vb = VideoBlock(id='X', title='T', channel='C', url='u', duration=60, upload_date='20260101')
header_m = format_header(meta)
header_v = format_header(vb)
assert header_m == header_v  # shared 4 fields are identical
assert '# T' in header_m and 'Channel: C' in header_m and 'Duration: 1:00' in header_m

print('ok')
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb
```

---

### Task 24: Export, full tests, grep verify

- [ ] **Step 1: Export**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-export
```

- [ ] **Step 2: Full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test
```

Expected: `Success.`.

- [ ] **Step 3: Grep — no Pydantic-shape subscript access remains in in-scope files**

```bash
cd /home/doyu/yttoc && grep -nE "(row|section|sec|s|meta|sums?)\[('|\")(path|title|start|end|summary|keywords|evidence|video|sections|full|duration|channel|upload_date|url|id|lesson|video_id|video_title|jump_url)(\1)\]" yttoc/core.py yttoc/map.py yttoc/summarize.py yttoc/ask.py yttoc/toc.py
```

Expected: no hits on Meta / VideoBlock / AssembledSummaries / NormalizedSection-or-subclass values. Any remaining subscript hits are on raw dicts like `llm_result['sections']` in `_assemble_summaries` — those operate on the LLM-result dict, not on a Pydantic-typed value. Verify each hit's context.

- [ ] **Step 4: `nbdev-prepare`**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-prepare
```

Expected: `Success.`.

---

### Task 25: Stage, review, commit, push, open PR-C

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/03_toc.ipynb nbs/04_summarize.ipynb nbs/05_map.ipynb yttoc/core.py yttoc/toc.py yttoc/summarize.py yttoc/map.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff**

```bash
git status && git diff --cached --stat && git diff --cached | head -500
```

- [ ] **Step 3: Pause for user review**

Ask: "PR-C staged diff ready. Approve to commit?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(map,core,toc,summarize): finalize Phase 2 type purity (PR-C)

PR-C of Phase 2d — completes the Phase 2 Pydantic migration.

Key changes:
- FlattenedSection(AssembledSection) added to yttoc.map; enables
  format_toc_line polymorphism for map's keyword/topic rows.
- load_summaries, flatten_sections, _build_keyword_index, and the
  three render_by_* functions in map.py switched to attribute access
  and typed (lesson, AssembledSummaries) tuples. The previous
  `doc['_lesson']` monkey-patch is gone.
- format_header signature: Meta | VideoBlock (string annotation to
  avoid core→summarize cycle). '| dict' shim removed.
- format_toc_line signature: NormalizedSection (accepts
  AssembledSection and FlattenedSection via inheritance
  polymorphism). Dict-typed signature removed.
- yttoc_toc, _print_section_summary, yttoc_sum all drop their
  .model_dump() adapters.
- New: integration test confirming polymorphism works across all
  section and header subclasses.

End state: every internal pipeline shape and every on-disk JSON
file in yttoc is Pydantic-validated on I/O and attribute-accessed
in consumers. Phase 2 complete.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2d-finalize
gh pr create --title "refactor(map,core,toc,summarize): finalize Phase 2 type purity (Phase 2d PR-C)" --body "$(cat <<'EOF'
## Summary

Phase 2d PR-C (of 3) — completes the entire Phase 2 Pydantic adoption. Types \`yttoc/map.py\` via \`FlattenedSection(AssembledSection)\` and finalizes the deferred type-purity cleanups for \`format_header\` and \`format_toc_line\`.

## End state

After this PR merges, every yttoc pipeline shape — in-memory and on-disk — is Pydantic-typed and validated at I/O boundaries:

- In-memory: \`Segment\`, \`NormalizedSection\`, \`AssembledSection\`, \`FlattenedSection\` (inheritance chain)
- On-disk: \`TocFile\` (toc.json), \`Meta\` (meta.json), \`AssembledSummaries\` (summaries.json)
- LLM I/O: \`RawTocSection\` / \`TocLLMResult\`, \`SummaryLLMResult\`, \`AskResponse\`, \`Citation\`, \`GetSummariesArgs\`, \`GetXscriptRangeArgs\`
- CLI display: \`format_header(meta: Meta | VideoBlock)\`, \`format_toc_line(section: NormalizedSection)\` — both strictly typed, subclass polymorphism covers all call sites

## Test plan

- [x] Full \`nbdev-test\` passes
- [x] New integration test: \`format_toc_line\` and \`format_header\` accept every typed subclass; all produce identical output for shared fields
- [x] Grep: no Pydantic-shape subscript access remains on typed values

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI + user merge + resync**

```bash
gh pr checks <PR_NUMBER>
# after merge:
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2d-finalize 2>/dev/null || true
```

---

### Task 26: Archive plan

**Files:** move `docs/superpowers/plans/2026-04-19-pydantic-phase2d-assembled-summaries.md` → `docs/superpowers/plans/done/`.

- [ ] **Step 1: After PR-C merges, create housekeeping PR**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main
git checkout -b chore/archive-phase2d-plan
git mv docs/superpowers/plans/2026-04-19-pydantic-phase2d-assembled-summaries.md docs/superpowers/plans/done/
git commit -m "chore(plans): archive Phase 2d AssembledSummaries plan (Phase 2 complete)"
git push -u origin chore/archive-phase2d-plan
gh pr create --title "chore(plans): archive Phase 2d plan (Phase 2 complete)" --body "All three Phase 2d implementation PRs are merged. Moving the plan under \`done/\`. Phase 2 of the Pydantic adoption is now complete."
```

- [ ] **Step 2: Merge + resync**

```bash
gh pr merge <PR_NUMBER> --rebase --delete-branch
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main
```

---

## Summary Checklist (end-state)

- [ ] PR-A merged: `VideoBlock`, `AssembledSection(NormalizedSection)`, `AssembledSummaries` in `yttoc.summarize`; `_assemble_summaries` uses them internally; public dict API preserved
- [ ] PR-B merged: `_assemble_summaries` + `generate_summaries` + `get_summaries` return `AssembledSummaries`; all 3 summaries.json read sites strict-validated; `_migrate_old_summaries` and Test 7 deleted; corruption + round-trip tests added; consumer attribute access in `summarize` and `ask`
- [ ] PR-C merged: `FlattenedSection(AssembledSection)` in `yttoc.map`; map.py fully typed (tuple-based, no monkey-patch); `format_header` → `Meta | VideoBlock`; `format_toc_line` → `NormalizedSection`; `.model_dump()` adapters gone; polymorphism integration test passes
- [ ] Plan archived under `docs/superpowers/plans/done/`
- [ ] Phase 2 of the yttoc Pydantic adoption complete
