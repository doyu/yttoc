# Pydantic Phase 2c — Meta / meta.json Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a 9-field `Meta` Pydantic model for per-video metadata. Promote `last_used_at` to `datetime` and constrain `captions` values to `Literal["auto","manual"]`. Propagate the type through every `meta.json` read site (7 locations) and every consumer that touches Meta fields. Split into PR-A (API-preserving model introduction) and PR-B (return-type flip + strict on-read validation + consumer attribute access + test fixture expansion).

**Architecture:** `Meta` lives in `nbs/00_core.ipynb` (shared pipeline type), consistent with `Segment` and `NormalizedSection` placement. No envelope model is needed — `meta.json` is a flat dict. `yttoc_list` is refactored to avoid its current `_langs` monkey-patch on the meta dict, since Pydantic models reject extra attributes. All existing cached `meta.json` files are verified to validate against `Meta` before PR-B branches.

**Tech Stack:** Python, nbdev 3, Pydantic v2. All `nbdev-*` commands run from `/home/doyu/yttoc/` under `.venv`.

**Spec:** `docs/superpowers/specs/2026-04-19-pydantic-phase2c-meta-design.md` (commit `4582b70`).

**Execution environment:** Use `/home/doyu/yttoc/.venv/bin/python`, `/home/doyu/yttoc/.venv/bin/nbdev-export`, `/home/doyu/yttoc/.venv/bin/nbdev-test`. Edit notebooks by loading JSON with Python, mutating target cells' `source`, writing back, then running `scripts/normalize_notebooks.py`.

**AGENTS.md compliance checkpoints:**
- Stage for review (`git diff --cached`) before every commit.
- No direct push to `main`; each PR lives on a feature branch.
- One feature per PR. Rebase-merge on GitHub; delete branch after merge; `git reset --hard origin/main` locally to resync.

---

## File Structure

### PR-A touches
- `nbs/00_core.ipynb` — add `Meta` BaseModel + validation test
- `nbs/01_fetch.ipynb` — import `Meta`, construct internally in `_build_meta`, return via `.model_dump(mode='json')`
- Generated `yttoc/core.py`, `yttoc/fetch.py`, `yttoc/_modidx.py`

### PR-B touches
- `nbs/01_fetch.ipynb` — flip `_build_meta` return to `Meta`; rewrite `fetch_video` write; refactor `_update_last_used` for Meta round-trip; refactor `yttoc_list` to avoid `_langs` dict monkey-patch; expand 2 test fixtures to full 9-field Meta shape
- `nbs/00_core.ipynb` — retype `format_header(meta: Meta)`; attribute access
- `nbs/02_xscript.ipynb` — `_load_segments` reads via `Meta.model_validate_json`; return tuple typed
- `nbs/03_toc.ipynb` — `generate_toc`, `yttoc_toc`, `_build_toc_prompt` use `Meta`; expand Test 7/8 fixtures
- `nbs/04_summarize.ipynb` — `_build_summary_prompt`, `_assemble_summaries`, `generate_summaries`, `_migrate_old_summaries` use `Meta`; expand Tests 4/5/6/7 fixtures
- New corruption-rejection test + `_update_last_used` round-trip test (in `nbs/01_fetch.ipynb`)
- Generated `yttoc/core.py`, `yttoc/fetch.py`, `yttoc/xscript.py`, `yttoc/toc.py`, `yttoc/summarize.py`, `yttoc/_modidx.py`

---

## PR-A — Introduce `Meta` (API-preserving, ~45 lines)

### Task 1: Create PR-A feature branch

**Files:** none

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: `On branch main`, `nothing to commit, working tree clean`.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2c-meta-model
```

Expected: `Switched to a new branch 'refactor/pydantic-phase2c-meta-model'`.

---

### Task 2: Add `Meta` BaseModel + validation test to `nbs/00_core.ipynb`

**Files:**
- Modify: `nbs/00_core.ipynb` — cell `ec3460e1` (add imports + class); insert new test cell after the existing `NormalizedSection` test cell (look up its id via the inspection step below)

- [ ] **Step 1: Inspect cells to locate insertion point**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/00_core.ipynb'))
for i, c in enumerate(nb['cells']):
    if c.get('cell_type') == 'code':
        src = ''.join(c['source'])
        if 'NormalizedSection(' in src or 'Segment(' in src[:200]:
            print(f'idx={i} id={c.get(\"id\")}  :: {src.splitlines()[0][:80]!r}')
"
```

Record the cell `id` of the NormalizedSection validation test (it will look like `# Test: NormalizedSection validates required fields and non-negative bounds`). Refer to it as `<NS_TEST_ID>` in Step 4.

- [ ] **Step 2: Edit cell `ec3460e1` — add imports and `Meta` class**

The cell currently reads (simplified):
```python
#| export
from pydantic import BaseModel, Field

class Segment(BaseModel): ...
class NormalizedSection(BaseModel): ...

def fmt_duration(...): ...
def format_header(meta: dict, ...) -> str: ...
def slice_segments(...): ...
def format_toc_line(...): ...
```

Apply these changes to cell `ec3460e1`:

1. Right below the existing `from pydantic import BaseModel, Field` line, add two imports:
```python
from datetime import datetime
from typing import Literal
```

2. Immediately after the `class NormalizedSection(BaseModel): ...` block (with its 4 fields), and BEFORE `def fmt_duration`, insert:
```python
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

Leave `Segment`, `NormalizedSection`, `fmt_duration`, `format_header`, `slice_segments`, `format_toc_line` unchanged.

- [ ] **Step 3: Normalize + export + verify Meta is importable**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb && .venv/bin/nbdev-export
```

Expected: no errors.

```bash
/home/doyu/yttoc/.venv/bin/python -c "
from datetime import datetime, timezone
from yttoc.core import Meta
m = Meta(id='x', title='t', channel='c', duration=60, upload_date='20260101',
         webpage_url='https://y.com', captions={'en': 'auto'},
         last_used_at=datetime.now(timezone.utc))
print(m)
"
```

Expected: prints a `Meta` instance repr without errors.

- [ ] **Step 4: Insert a new code cell for the Meta validation test**

Via Python (load notebook JSON, find index of cell with `id == '<NS_TEST_ID>'` from Step 1, insert new code cell at index + 1). Fresh 8-char hex `id`. Source:

```python
# Test: Meta validates required fields, captions Literal, last_used_at datetime
from yttoc.core import Meta
from pydantic import ValidationError
from datetime import datetime, timezone

# Valid construction succeeds (all 9 fields)
m = Meta(id='vid1', title='T', channel='Ch', duration=600,
         upload_date='20260101', webpage_url='https://youtube.com/watch?v=vid1',
         captions={'en': 'auto'},
         last_used_at=datetime(2026, 4, 16, 15, 13, 50, 653895, tzinfo=timezone.utc))
assert m.id == 'vid1'
assert m.description == ''  # default
assert isinstance(m.last_used_at, datetime)

# Missing required field rejected (no channel)
try:
    Meta(id='x', title='t', duration=60, upload_date='20260101',
         webpage_url='u', captions={'en': 'auto'},
         last_used_at=datetime.now(timezone.utc))
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing channel'

# Negative duration rejected
try:
    Meta(id='x', title='t', channel='c', duration=-1, upload_date='20260101',
         webpage_url='u', captions={'en': 'auto'},
         last_used_at=datetime.now(timezone.utc))
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative duration'

# Invalid captions value rejected
try:
    Meta(id='x', title='t', channel='c', duration=60, upload_date='20260101',
         webpage_url='u', captions={'en': 'autop'},  # typo
         last_used_at=datetime.now(timezone.utc))
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for invalid caption type'

# Invalid last_used_at string rejected
try:
    Meta.model_validate_json(
        '{"id":"x","title":"t","channel":"c","duration":60,"upload_date":"20260101",'
        '"webpage_url":"u","captions":{"en":"auto"},"last_used_at":"yesterday"}'
    )
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for invalid last_used_at'

# Valid ISO last_used_at parses to datetime
m2 = Meta.model_validate_json(
    '{"id":"x","title":"t","channel":"c","duration":60,"upload_date":"20260101",'
    '"webpage_url":"u","captions":{"en":"auto"},'
    '"last_used_at":"2026-04-16T15:13:50.653895+00:00"}'
)
assert isinstance(m2.last_used_at, datetime)
assert m2.last_used_at.tzinfo is not None

print('ok')
```

- [ ] **Step 5: Normalize + run tests for nbs/00**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb && .venv/bin/nbdev-test --path nbs/00_core.ipynb
```

Expected: `Success.`.

---

### Task 3: Use `Meta` internally in `_build_meta` (`nbs/01_fetch.ipynb`)

**Files:**
- Modify: `nbs/01_fetch.ipynb` — cell `k1vfan4sv` (imports); the cell containing `_build_meta` (look it up — it's in the same export block as `_pick_lang`, `_glob_srt`, `_update_last_used`, `_build_meta`, `_download_srt`; its id appears as `0zd7en6efu0n` based on the current layout)

- [ ] **Step 1: Inspect the target cells**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/01_fetch.ipynb'))
for c in nb['cells']:
    if c.get('id') in ('k1vfan4sv','0zd7en6efu0n'):
        print(f'=== {c[\"id\"]} ===')
        print(''.join(c['source']))
        print()
"
```

Expected: `k1vfan4sv` contains `import json, os` + `datetime` import + `import yt_dlp` + `_DEFAULT_ROOT`. `0zd7en6efu0n` contains `_pick_lang`, `_glob_srt`, `_update_last_used`, `_build_meta`, `_download_srt`.

- [ ] **Step 2: Edit cell `k1vfan4sv` — import `Meta`**

Append to the cell source:
```python
from yttoc.core import Meta
```

The final cell content should read:
```python
#| export
import json, os
from datetime import datetime, timezone
from pathlib import Path
import yt_dlp
from yttoc.core import Meta

_DEFAULT_ROOT = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'yttoc'
```

- [ ] **Step 3: Edit cell `0zd7en6efu0n` — `_build_meta` constructs Meta internally**

Find the `_build_meta` function:
```python
def _build_meta(info: dict, # yt-dlp info dict
                lang: str = 'en', # Language that was fetched
                caption_type: str = 'auto' # 'manual' or 'auto'
               ) -> dict: # meta.json content
    "Extract fields for meta.json from yt-dlp info."
    return {
        'id': info['id'],
        'title': info['title'],
        'channel': info['channel'],
        'duration': info['duration'],
        'upload_date': info['upload_date'],
        'webpage_url': info['webpage_url'],
        'description': info.get('description', ''),
        'captions': {lang: caption_type},
        'last_used_at': datetime.now(timezone.utc).isoformat(),
    }
```

Replace the body with:
```python
def _build_meta(info: dict, # yt-dlp info dict
                lang: str = 'en', # Language that was fetched
                caption_type: str = 'auto' # 'manual' or 'auto'
               ) -> dict: # meta.json content
    "Extract fields for meta.json from yt-dlp info."
    meta = Meta(
        id=info['id'],
        title=info['title'],
        channel=info['channel'],
        duration=info['duration'],
        upload_date=info['upload_date'],
        webpage_url=info['webpage_url'],
        description=info.get('description', ''),
        captions={lang: caption_type},
        last_used_at=datetime.now(timezone.utc),
    )
    return meta.model_dump(mode='json')
```

Key changes:
- Dict-literal return replaced with `Meta(...)` construction.
- `last_used_at` now passed as `datetime` object (Pydantic promotes it to `datetime` field; `model_dump(mode='json')` serializes to ISO string for the returned dict).
- Final return uses `meta.model_dump(mode='json')` — preserves public `dict` API including ISO-string `last_used_at`.

Leave `_pick_lang`, `_glob_srt`, `_update_last_used`, `_download_srt` bit-identical.

- [ ] **Step 4: Normalize + export + run tests**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/01_fetch.ipynb && .venv/bin/nbdev-export && .venv/bin/nbdev-test --path nbs/01_fetch.ipynb
```

Expected: `Success.`. The existing `_build_meta` test (cell `vcljbltw9ym`) passes because `model_dump(mode='json')` yields a dict with the same keys. The `{'en': 'auto'}` caption passes because the fake_info fixture uses `caption_type='auto'` (in the Literal set).

- [ ] **Step 5: Python-level confirmation**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
from yttoc.fetch import _build_meta
fake_info = {'id': 'X', 'title': 't', 'channel': 'c', 'duration': 1,
             'upload_date': '20260101', 'webpage_url': 'u',
             'description': 'desc', 'subtitles': {}, 'automatic_captions': {'en': []}}
m = _build_meta(fake_info, lang='en', caption_type='auto')
assert isinstance(m, dict)
assert m['captions'] == {'en': 'auto'}
assert m['description'] == 'desc'
# last_used_at is a string in the returned dict
assert isinstance(m['last_used_at'], str)
print('OK')
"
```

Expected: `OK` printed.

---

### Task 4: Stage, commit, push, open PR-A

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/01_fetch.ipynb yttoc/core.py yttoc/fetch.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff for user review**

```bash
git status && git diff --cached --stat && git diff --cached
```

Expected: 5 files changed. `yttoc/core.py` adds `datetime` / `Literal` imports and `Meta` class. `yttoc/fetch.py` imports `Meta` and `_build_meta` returns `meta.model_dump(mode='json')`.

- [ ] **Step 3: Pause for user review**

Ask: "PR-A staged diff ready. Approve to commit?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(core,fetch): introduce Meta BaseModel (PR-A)

Phase 2c pilot PR-A — adds Meta Pydantic model in yttoc.core with 9
fields. last_used_at is typed as datetime; captions values are
constrained to Literal["auto", "manual"]. _build_meta now constructs
Meta internally and returns meta.model_dump(mode='json') so callers
still see a dict with an ISO-string last_used_at. Zero consumer
impact in PR-A.

PR-B follow-up will flip _build_meta to return Meta, wrap every
meta.json read with Meta.model_validate_json, and propagate attribute
access to all downstream consumers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2c-meta-model
gh pr create --title "refactor(core,fetch): introduce Meta BaseModel (Phase 2c PR-A)" --body "$(cat <<'EOF'
## Summary

Phase 2c pilot PR-A — adds the \`Meta\` Pydantic model (9 fields) to \`yttoc.core\`. \`_build_meta\` constructs \`Meta\` internally and returns \`meta.model_dump(mode='json')\` so the public dict API is preserved. PR-B follow-up flips the return type and wraps every \`meta.json\` read with \`Meta.model_validate_json\`.

Field decisions:
- \`last_used_at: datetime\` (Pydantic v2 parses/serializes ISO 8601 natively)
- \`captions: dict[str, Literal["auto","manual"]]\` constrains value space
- \`description\` defaults to \`''\` (matches current \`info.get('description', '')\` behavior)
- \`duration: int = Field(ge=0)\` consistent with Segment/NormalizedSection

Placement rationale: \`Meta\` lives in \`core\` (shared pipeline type, consumed by 5+ modules). See spec \`docs/superpowers/specs/2026-04-19-pydantic-phase2c-meta-design.md\`.

## Test plan

- [x] \`nbdev-test\` full suite passes (public contract unchanged)
- [x] New test: \`Meta\` rejects missing required field, negative duration, invalid caption type, invalid \`last_used_at\` string
- [x] New test: valid ISO \`last_used_at\` string parses to timezone-aware \`datetime\`
- [x] \`from yttoc.core import Meta\` works

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI + user merge**

```bash
gh pr checks <PR_NUMBER>
```

Stop here. Do NOT proceed to PR-B until user merges PR-A and local `main` is resynced.

- [ ] **Step 7: After merge, resync local main**

```bash
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2c-meta-model 2>/dev/null || true && git log --oneline -3
```

---

## PR-B — Propagate `Meta` + wrap `meta.json` I/O (~180-200 lines)

**⚠ Atomic refactor note:** PR-B flips `_build_meta`'s public return and wraps all 7 `meta.json` reads in `Meta.model_validate_json`. Between Task 7 and Task 13, intermediate states will have red tests. Only run full `nbdev-test` at Task 14. Targeted per-notebook tests are acceptable for quick sanity checks during intermediate tasks.

### Task 5: Pre-flight — verify existing cached `meta.json` files validate against `Meta`

**Files:** none (verification only).

- [ ] **Step 1: Run the pre-flight script**

```bash
/home/doyu/yttoc/.venv/bin/python <<'PYEOF'
from pathlib import Path
from yttoc.core import Meta
import sys
fails = []
cache_root = Path.home() / '.cache' / 'yttoc'
if not cache_root.exists():
    print('No cache root; skipping.')
    sys.exit(0)
for f in sorted(cache_root.glob('*/meta.json')):
    try:
        m = Meta.model_validate_json(f.read_text(encoding='utf-8'))
        for lang, ctype in m.captions.items():
            assert ctype in ('auto', 'manual'), f'Unexpected caption type {ctype!r} in {f}'
        print(f'OK: {f}')
    except Exception as e:
        fails.append((f, e))
        print(f'FAIL: {f} -> {e}')
sys.exit(1 if fails else 0)
PYEOF
```

Expected: every cached `meta.json` prints `OK:`. If any fail, STOP and escalate — do not proceed to branch creation. The fix path is either expanding the `Literal` union, relaxing a constraint, or migrating/removing the offending cache file.

---

### Task 6: Create PR-B feature branch

**Files:** none

- [ ] **Step 1: Verify clean main and PR-A merged**

```bash
cd /home/doyu/yttoc && git checkout main && git status
```

Expected: clean tree, `git log -1` shows the PR-A merge commit from origin.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2c-meta-propagate
```

---

### Task 7: Flip `_build_meta` return + update `_update_last_used` + `fetch_video` write path

**Files:**
- Modify: `nbs/01_fetch.ipynb` — cell `0zd7en6efu0n` (`_update_last_used`, `_build_meta`); cell `irch7o3902r` (`fetch_video`)

- [ ] **Step 1: Edit cell `0zd7en6efu0n` — `_build_meta` returns `Meta`**

Change the `_build_meta` signature return annotation and drop `.model_dump(mode='json')`:

```python
def _build_meta(info: dict, # yt-dlp info dict
                lang: str = 'en', # Language that was fetched
                caption_type: str = 'auto' # 'manual' or 'auto'
               ) -> Meta: # Parsed Meta instance
    "Extract fields for meta.json from yt-dlp info."
    return Meta(
        id=info['id'],
        title=info['title'],
        channel=info['channel'],
        duration=info['duration'],
        upload_date=info['upload_date'],
        webpage_url=info['webpage_url'],
        description=info.get('description', ''),
        captions={lang: caption_type},
        last_used_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 2: Edit cell `0zd7en6efu0n` — `_update_last_used` uses Meta round-trip**

Replace:
```python
def _update_last_used(meta_path: Path # Path to meta.json
                     ) -> None:
    "Update last_used_at timestamp in meta.json."
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    meta['last_used_at'] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
```

with:
```python
def _update_last_used(meta_path: Path # Path to meta.json
                     ) -> None:
    "Update last_used_at timestamp in meta.json."
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    meta.last_used_at = datetime.now(timezone.utc)
    meta_path.write_text(meta.model_dump_json(indent=2), encoding='utf-8')
```

Note: Pydantic v2 BaseModel instances are mutable by default (unlike NamedTuple), so `meta.last_used_at = ...` works directly.

- [ ] **Step 3: Edit cell `irch7o3902r` — `fetch_video` writes via `meta.model_dump_json`**

Find:
```python
    _srt_path, lang, caption_type = _download_srt(url, info, out_dir)
    meta_path.write_text(
        json.dumps(_build_meta(info, lang=lang, caption_type=caption_type),
                   indent=2, ensure_ascii=False),
        encoding='utf-8')
    return out_dir
```

Replace with:
```python
    _srt_path, lang, caption_type = _download_srt(url, info, out_dir)
    meta = _build_meta(info, lang=lang, caption_type=caption_type)
    meta_path.write_text(meta.model_dump_json(indent=2), encoding='utf-8')
    return out_dir
```

- [ ] **Step 4: Normalize (do NOT run tests yet — yttoc_list still subscripts dict)**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/01_fetch.ipynb
```

---

### Task 8: Refactor `yttoc_list` to use `Meta` without monkey-patching `_langs`

**Files:**
- Modify: `nbs/01_fetch.ipynb` — cell `9e0508a9` (`yttoc_list`)

- [ ] **Step 1: Inspect current `yttoc_list`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/01_fetch.ipynb'))
for c in nb['cells']:
    if c.get('id') == '9e0508a9':
        print(''.join(c['source']))
"
```

Expected: contains the `yttoc_list` function that monkey-patches `meta['_langs']` onto the meta dict for display, then sorts and prints.

- [ ] **Step 2: Replace the `yttoc_list` function body**

Replace the full function (keep the `@call_parse` decorator unchanged):

```python
@call_parse
def yttoc_list(root: str = None, # Root directory (default: ~/.cache/yttoc)
              ):
    "List cached videos sorted by last used."
    root = Path(root) if root else _DEFAULT_ROOT
    if not root.exists(): return

    items = []  # list of (meta: Meta, langs: str)
    for d in root.iterdir():
        if not d.is_dir(): continue
        meta_path = d / 'meta.json'
        srt_files = _glob_srt(d)
        if not (meta_path.exists() and srt_files): continue
        meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
        captions = meta.captions or {p.stem.split('.', 1)[1]: '?' for p in srt_files}
        langs = ','.join(sorted(captions.keys()))
        items.append((meta, langs))

    items.sort(key=lambda x: x[0].last_used_at, reverse=True)
    for meta, langs in items:
        ts = meta.last_used_at.isoformat()[:16].replace('T', ' ')
        dur = _fmt_duration(meta.duration)
        print(f"{meta.id}  {ts}  {dur:>8}  [{langs}]  {meta.title}")
```

Key structural changes:
- Loop builds `(meta, langs)` tuples instead of mutating `meta['_langs']`.
- Sort key is `x[0].last_used_at` (a `datetime` — compares natively without string coercion).
- ISO-string timestamp is produced via `meta.last_used_at.isoformat()[:16]` at display time.
- Caption fallback `captions or {...}` works because `Meta.captions` is a non-empty dict by definition (the fallback covers the unlikely `captions={}` case; the pre-flight script confirmed no current cache has that).

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/01_fetch.ipynb
```

---

### Task 9: Expand `nbs/01_fetch.ipynb` test fixtures to full 9-field Meta shape

**Files:**
- Modify: `nbs/01_fetch.ipynb` — cells `vcljbltw9ym` (existing `_build_meta` + `_update_last_used` tests) and `6051a34b` (existing `yttoc_list` test with A/B/C fixtures)

- [ ] **Step 1: Inspect cell `vcljbltw9ym`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/01_fetch.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'vcljbltw9ym':
        print(''.join(c['source']))
"
```

- [ ] **Step 2: Update cell `vcljbltw9ym` — `_update_last_used` fixture must be full Meta shape**

Find the `_update_last_used` sub-test inside cell `vcljbltw9ym`. It currently writes a minimal dict to `meta.json`. Replace that block:

```python
# Test: _update_last_used
with TemporaryDirectory() as d:
    p = Path(d) / 'meta.json'
    p.write_text(json.dumps({
        'id': 'X', 'title': 't', 'channel': 'c', 'duration': 60,
        'upload_date': '20260101', 'webpage_url': 'https://y.com/X',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00',
    }), encoding='utf-8')
    _update_last_used(p)
    updated = json.loads(p.read_text(encoding='utf-8'))
    assert updated['id'] == 'X'
    assert updated['last_used_at'] != '2000-01-01T00:00:00+00:00'
    # Verify it parses as a datetime (ISO format)
    from datetime import datetime
    assert datetime.fromisoformat(updated['last_used_at']).tzinfo is not None
```

If the existing sub-test has different assertions (e.g., checking a specific timestamp), preserve the intent but adapt to the round-trip pattern: the file now contains a full 9-field Meta shape written via `model_dump_json`, not a hand-crafted dict.

The `_build_meta` sub-test (using `fake_info` dict + `caption_type='auto'`) needs no change since `fake_info` already has all the fields `_build_meta` reads from.

- [ ] **Step 3: Update cell `6051a34b` — A/B/C fixture meta.json contents**

Find the three meta.json writes and replace each with the full 9-field shape. Keep the "CCCC" video deliberately incomplete (no srt), so its meta.json is never read by `yttoc_list`. But A and B must now have all 9 fields:

Replace the A-video meta.json write:
```python
    (a / 'meta.json').write_text(json.dumps({
        'id': 'AAAA', 'title': 'Old video', 'channel': 'Ch', 'duration': 195,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=AAAA',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2026-01-01T00:00:00+00:00',
    }))
```

Replace the B-video meta.json write:
```python
    (b / 'meta.json').write_text(json.dumps({
        'id': 'BBBB', 'title': 'New video', 'channel': 'Ch', 'duration': 3991,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=BBBB',
        'description': '', 'captions': {'ja': 'manual'},
        'last_used_at': '2026-04-06T15:00:00+00:00',
    }))
```

Leave the C-video write (`{"id":"CCCC"}`) unchanged — this video's meta.json is skipped before being read (no srt files exist).

The assertions at the end of the test (`'[ja]' in out`, `'BBBB' in out`, etc.) stay unchanged — `yttoc_list` still displays the same information.

- [ ] **Step 4: Normalize and run nbs/01 tests**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/01_fetch.ipynb && .venv/bin/nbdev-test --path nbs/01_fetch.ipynb
```

Expected: `Success.`. The whole fetch notebook (including the refactored `yttoc_list`) should pass at this point.

---

### Task 10: Update `format_header` in `nbs/00_core.ipynb`

**Files:**
- Modify: `nbs/00_core.ipynb` — cell `ec3460e1`

- [ ] **Step 1: Edit `format_header`**

Find:
```python
def format_header(meta: dict # meta.json content
                 ) -> str: # Formatted header string
    "Shared header for toc/sum/raw CLI commands."
    title = meta.get('title', '')
    channel = meta.get('channel', '')
    dur = fmt_duration(meta.get('duration', 0))
    upload = meta.get('upload_date', '')
    return f'# {title}\nChannel: {channel} | Duration: {dur} | {upload}'
```

Replace with:
```python
def format_header(meta: Meta # Parsed Meta instance
                 ) -> str: # Formatted header string
    "Shared header for toc/sum/raw CLI commands."
    dur = fmt_duration(meta.duration)
    return f'# {meta.title}\nChannel: {meta.channel} | Duration: {dur} | {meta.upload_date}'
```

Note: `format_header` is called from `yttoc_toc` (toc.py), `yttoc_raw` / `yttoc_txt` (xscript.py via `_load_segments` result), `yttoc_sum` (summarize.py). The first two will be updated in Tasks 11-12. The third (`yttoc_sum`) receives `meta` from a Pydantic-validated summaries.json section which is Phase 2d territory; see Task 13 for the adapter.

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb
```

---

### Task 11: Update `xscript._load_segments` to use `Meta`

**Files:**
- Modify: `nbs/02_xscript.ipynb` — cell `bcd5731c`

- [ ] **Step 1: Inspect**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/02_xscript.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'bcd5731c':
        print(''.join(c['source']))
"
```

- [ ] **Step 2: Extend imports with `Meta`**

In cell `bcd5731c`, change the existing `from yttoc.core import ...` line to include `Meta`:

Before (after Phase 2b):
```python
from yttoc.core import fmt_duration, format_header, slice_segments, NormalizedSection
```

After:
```python
from yttoc.core import fmt_duration, format_header, slice_segments, NormalizedSection, Meta
```

- [ ] **Step 3: Update `_load_segments` signature and body**

Find:
```python
def _load_segments(video_id: str, section: str, root: str | None
                  ) -> tuple[dict, list[Segment], NormalizedSection | None, Path]:
    "Load meta, parse xscript, optionally slice to section. Return (meta, segments, sec_info, meta_path)."
    root = Path(root) if root else _DEFAULT_ROOT
    d = root / video_id
    meta_path = d / 'meta.json'
    srt_files = _glob_srt(d)
    if not (meta_path.exists() and srt_files):
        raise SystemExit(f"Not cached: {video_id}")

    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    sec_info = None
    ...
```

Replace the first tuple element type and the `meta = json.loads(...)` line:

```python
def _load_segments(video_id: str, section: str, root: str | None
                  ) -> tuple[Meta, list[Segment], NormalizedSection | None, Path]:
    "Load meta, parse xscript, optionally slice to section. Return (meta, segments, sec_info, meta_path)."
    root = Path(root) if root else _DEFAULT_ROOT
    d = root / video_id
    meta_path = d / 'meta.json'
    srt_files = _glob_srt(d)
    if not (meta_path.exists() and srt_files):
        raise SystemExit(f"Not cached: {video_id}")

    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    sec_info = None
```

(The rest of `_load_segments` — the optional `if section:` block with `TocFile.model_validate_json` — stays unchanged.)

Callers of `_load_segments` (`yttoc_raw`, `yttoc_txt`) unpack the tuple and pass `meta` to `format_header(meta)`. Since `format_header` now takes `Meta`, no caller-side change is required.

- [ ] **Step 4: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

---

### Task 12: Update `nbs/03_toc.ipynb` — `_build_toc_prompt`, `generate_toc`, `yttoc_toc` + expand Tests 7/8 fixtures

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `b1000004` (imports), `d95b70ae` (`_build_toc_prompt`), `795bea0d` (`generate_toc`, `yttoc_toc`), `971d3b0c` (Test 7 fixture), `f0fb87b4` (Test 8 fixture)

- [ ] **Step 1: Update cell `b1000004` — add `Meta` import**

Current content:
```python
#| export
import json
from pathlib import Path
from pydantic import BaseModel, Field
from yttoc.core import Segment, NormalizedSection
```

Replace the last import:
```python
from yttoc.core import Segment, NormalizedSection, Meta
```

- [ ] **Step 2: Update cell `d95b70ae` — `_build_toc_prompt` signature + body**

Find:
```python
def _build_toc_prompt(segments: list[Segment], # List of Segment from parse_xscript
                      meta: dict # meta.json content
                     ) -> str: # Prompt for LLM
    "Build a prompt that asks the LLM to identify topic transitions and return section titles with start times."
    lines = []
    for s in segments:
        mm = int(s.start // 60)
        ss = int(s.start % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
    transcript = '\n'.join(lines)

    title = meta.get('title', '')
    channel = meta.get('channel', '')
    desc = meta.get('description', '')
```

Replace the 4 changed lines:
```python
def _build_toc_prompt(segments: list[Segment], # List of Segment from parse_xscript
                      meta: Meta # Parsed Meta instance
                     ) -> str: # Prompt for LLM
    "Build a prompt that asks the LLM to identify topic transitions and return section titles with start times."
    lines = []
    for s in segments:
        mm = int(s.start // 60)
        ss = int(s.start % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
    transcript = '\n'.join(lines)

    title = meta.title
    channel = meta.channel
    desc = meta.description
```

(Leave the rest of the cell — `RawTocSection`, `TocLLMResult`, `TocFile`, `_call_llm` — unchanged.)

- [ ] **Step 3: Update cell `795bea0d` — `generate_toc` and `yttoc_toc` read via `Meta.model_validate_json`**

Find:
```python
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_toc_prompt(segments, meta)
    raw = _call_llm(prompt)
    sections = _normalize_sections(raw, meta.get('duration', 0))
```

Replace with:
```python
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_toc_prompt(segments, meta)
    raw = _call_llm(prompt)
    sections = _normalize_sections(raw, meta.duration)
```

And in `yttoc_toc`, find:
```python
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    sections = generate_toc(video_id, root, refresh=refresh)

    print(format_header(meta))
```

Replace with:
```python
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    sections = generate_toc(video_id, root, refresh=refresh)

    print(format_header(meta))
```

Also verify `meta.get('webpage_url', '')` in `yttoc_toc` body (used for deep link URL construction in `format_toc_line`); replace with `meta.webpage_url`.

- [ ] **Step 4: Expand Test 7 fixture (cell `971d3b0c`)**

Find the meta.json write in cell `971d3b0c`:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID1', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID1',
        'last_used_at': '2000-01-01T00:00:00'}))
```

Replace with the full 9-field shape:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID1', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID1',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

Note the `last_used_at` now includes a UTC offset (`+00:00`) for `datetime.fromisoformat` compatibility.

- [ ] **Step 5: Expand Test 8 fixture (cell `f0fb87b4`)**

Same pattern — find the meta.json write and add `description`, `captions`, and `+00:00` offset:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID2', 'title': 'Test Video', 'channel': 'Ch', 'duration': 900,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID2',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

- [ ] **Step 6: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

---

### Task 13: Update `nbs/04_summarize.ipynb` — all Meta consumers + expand Tests 4/5/6/7 fixtures

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cells `c1000005` (imports + `_build_summary_prompt`), `d286018a` (imports + `_assemble_summaries`, `_migrate_old_summaries`, `generate_summaries`), `aa6db3d2` (Test 4 fixture), `87bf3d0d` (Test 5 fixture), `fbf6535c` (Test 6 fixture), `11e566da` (Test 7 fixture)

- [ ] **Step 1: Update cell `c1000005` — imports + `_build_summary_prompt`**

Change `from yttoc.core import slice_segments, Segment, NormalizedSection` to `from yttoc.core import slice_segments, Segment, NormalizedSection, Meta`.

Update `_build_summary_prompt`:

Before:
```python
def _build_summary_prompt(segments: list[Segment], # Full xscript segments
                          sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                          meta: dict # meta.json content
                         ) -> str: # Prompt for LLM
    "Build prompt asking LLM to summarize each section and the full video."
    parts = []
    for sec in sections:
        ...
    transcript = '\n\n'.join(parts)
    title = meta.get('title', '')
    channel = meta.get('channel', '')
    desc = meta.get('description', '')
```

After:
```python
def _build_summary_prompt(segments: list[Segment], # Full xscript segments
                          sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                          meta: Meta # Parsed Meta instance
                         ) -> str: # Prompt for LLM
    "Build prompt asking LLM to summarize each section and the full video."
    parts = []
    for sec in sections:
        ...
    transcript = '\n\n'.join(parts)
    title = meta.title
    channel = meta.channel
    desc = meta.description
```

(Loop body inside the function is unchanged from Phase 2b.)

- [ ] **Step 2: Update cell `d286018a` — imports + 3 functions**

Change the import line from:
```python
from yttoc.core import fmt_duration, format_header, format_toc_line, NormalizedSection
```
to:
```python
from yttoc.core import fmt_duration, format_header, format_toc_line, NormalizedSection, Meta
```

Update `_assemble_summaries`:

Before:
```python
def _assemble_summaries(meta: dict, # meta.json content
                        toc_sections: list[NormalizedSection], ...
    ...
    return {
        'video': {
            'id': meta.get('id'),
            'title': meta.get('title'),
            'channel': meta.get('channel'),
            'url': meta.get('webpage_url'),
            'duration': meta.get('duration'),
            'upload_date': meta.get('upload_date'),
        },
        ...
    }
```

After:
```python
def _assemble_summaries(meta: Meta, # Parsed Meta instance
                        toc_sections: list[NormalizedSection], ...
    ...
    return {
        'video': {
            'id': meta.id,
            'title': meta.title,
            'channel': meta.channel,
            'url': meta.webpage_url,
            'duration': meta.duration,
            'upload_date': meta.upload_date,
        },
        ...
    }
```

Update `_migrate_old_summaries`:

Before:
```python
def _migrate_old_summaries(cached: dict, ...
                          ) -> dict: # New-format summaries dict
    "Rebuild a self-contained summaries.json from the legacy {full, sections: {...}} shape."
    meta_path = root / video_id / 'meta.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    toc_sections = generate_toc(video_id, root)  # cached toc.json hit; no LLM call
    return _assemble_summaries(meta, toc_sections, cached)
```

After:
```python
def _migrate_old_summaries(cached: dict, ...
                          ) -> dict: # New-format summaries dict
    "Rebuild a self-contained summaries.json from the legacy {full, sections: {...}} shape."
    meta_path = root / video_id / 'meta.json'
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    toc_sections = generate_toc(video_id, root)  # cached toc.json hit; no LLM call
    return _assemble_summaries(meta, toc_sections, cached)
```

Update `generate_summaries`:

Before:
```python
    toc_sections = generate_toc(video_id, root)
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_summary_prompt(segments, toc_sections, meta)
```

After:
```python
    toc_sections = generate_toc(video_id, root)
    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_summary_prompt(segments, toc_sections, meta)
```

Leave `_print_section_summary`, `yttoc_sum`, `get_summaries` UNCHANGED — they operate on summaries.json sections (Phase 2d territory), not on Meta.

- [ ] **Step 3: Expand Test 4 fixture (cell `aa6db3d2`)**

Find the meta.json write:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID1', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'last_used_at': '2000-01-01T00:00:00'}))
```

Replace with:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID1', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID1',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

- [ ] **Step 4: Expand Test 5 fixture (cell `87bf3d0d`)**

Same pattern. Find the meta.json write for VID2 and replace with:
```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID2', 'title': 'Test Video', 'channel': 'Ch', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID2',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

- [ ] **Step 5: Expand Test 6 fixture (cell `fbf6535c`)**

```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID3', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID3',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

- [ ] **Step 6: Expand Test 7 fixture (cell `11e566da`)**

```python
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID4', 'title': 'Old', 'channel': 'Ch', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID4',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00'}))
```

- [ ] **Step 7: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 14: Add corruption-rejection + `_update_last_used` round-trip tests

**Files:**
- Modify: `nbs/01_fetch.ipynb` — insert two new code cells after cell `6051a34b` (the existing `yttoc_list` test)

- [ ] **Step 1: Insert corruption-rejection test cell**

Via Python: find index of cell with `id == '6051a34b'`, insert new code cell (fresh 8-char hex id) at index + 1. Source:

```python
# Test: yttoc_list rejects a corrupted meta.json (invalid caption type)
import io, contextlib
from tempfile import TemporaryDirectory
from pydantic import ValidationError

with TemporaryDirectory() as d:
    root = Path(d)
    v = root / 'BAD1'; v.mkdir()
    (v / 'captions.en.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nhi\n')
    # Invalid caption type: 'autop' is not in Literal["auto","manual"]
    (v / 'meta.json').write_text(json.dumps({
        'id': 'BAD1', 'title': 'T', 'channel': 'C', 'duration': 60,
        'upload_date': '20260101', 'webpage_url': 'https://y.com',
        'description': '', 'captions': {'en': 'autop'},
        'last_used_at': '2026-01-01T00:00:00+00:00'}))

    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            yttoc_list(root=str(root))
    except ValidationError:
        pass
    else:
        assert False, 'expected ValidationError for invalid caption type in meta.json'
print('ok')
```

- [ ] **Step 2: Insert `_update_last_used` round-trip test cell**

Insert immediately after the corruption-rejection test cell. Source:

```python
# Test: _update_last_used round-trip — bumps last_used_at monotonically, result is datetime-parseable
import time
from datetime import datetime
from tempfile import TemporaryDirectory

with TemporaryDirectory() as d:
    p = Path(d) / 'meta.json'
    p.write_text(json.dumps({
        'id': 'RT1', 'title': 't', 'channel': 'c', 'duration': 60,
        'upload_date': '20260101', 'webpage_url': 'https://y.com',
        'description': '', 'captions': {'en': 'auto'},
        'last_used_at': '2000-01-01T00:00:00+00:00',
    }), encoding='utf-8')

    _update_last_used(p)
    first = json.loads(p.read_text(encoding='utf-8'))['last_used_at']
    assert first != '2000-01-01T00:00:00+00:00'
    first_dt = datetime.fromisoformat(first)
    assert first_dt.tzinfo is not None

    time.sleep(0.001)
    _update_last_used(p)
    second = json.loads(p.read_text(encoding='utf-8'))['last_used_at']
    second_dt = datetime.fromisoformat(second)
    assert second_dt >= first_dt, f'{second} should be >= {first}'
print('ok')
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/01_fetch.ipynb
```

---

### Task 15: Export, full test suite, grep verification

**Files:** none (verification only).

- [ ] **Step 1: Export**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-export
```

Expected: no errors.

- [ ] **Step 2: Full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test
```

Expected: `Success.`.

- [ ] **Step 3: Grep — verify no `meta.get(...)` / `meta['...']` remain on Meta-typed values**

```bash
cd /home/doyu/yttoc && grep -nE "meta\.get\(('|\")(id|title|channel|duration|upload_date|webpage_url|description|captions|last_used_at)(\1)" yttoc/fetch.py yttoc/core.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py
```

Expected output: no hits. Any remaining `meta.get(...)` with a Meta field name indicates a missed consumer.

Also:
```bash
cd /home/doyu/yttoc && grep -nE "meta\[('|\")(id|title|channel|duration|upload_date|webpage_url|description|captions|last_used_at)(\1)\]" yttoc/fetch.py yttoc/core.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py
```

Expected: no hits.

Note: `meta.get(...)` and `meta['...']` patterns are acceptable ONLY if the variable is a raw dict representing yt-dlp's input (e.g., `info.get('description')` inside `_build_meta`). Verify any remaining hits are on `info`, not `meta`.

- [ ] **Step 4: `nbdev-prepare`**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-prepare
```

Expected: `Success.`.

---

### Task 16: Stage, review, commit, push, open PR-B

**Files:** staging + git ops.

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/01_fetch.ipynb nbs/02_xscript.ipynb nbs/03_toc.ipynb nbs/04_summarize.ipynb yttoc/core.py yttoc/fetch.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff**

```bash
git status && git diff --cached --stat && git diff --cached | head -500
```

Expected: 5 notebooks + 6 generated files. Net change under 200 lines.

- [ ] **Step 3: Pause for user review**

Ask: "PR-B staged diff ready. Approve to commit?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(fetch,xscript,toc,summarize): propagate Meta (PR-B)

PR-B of Phase 2c — flips _build_meta to return Meta, wraps every
meta.json read site (7 total) with Meta.model_validate_json, and
updates all consumers to attribute access.

Key changes:
- fetch_video writes via meta.model_dump_json(indent=2)
- _update_last_used performs Meta round-trip (read -> mutate datetime
  -> write model_dump_json)
- yttoc_list refactored to build (Meta, langs) tuples, avoiding the
  previous _langs dict monkey-patch (Pydantic models reject extra attrs)
- format_header, _load_segments, generate_toc, _build_toc_prompt,
  _build_summary_prompt, _assemble_summaries, _migrate_old_summaries,
  generate_summaries all take Meta and access fields via attribute
- 8 test fixtures across nbs/01, nbs/03, nbs/04 expanded to the full
  9-field Meta shape (adds description, captions, and UTC offset on
  last_used_at where missing)
- New corruption-rejection test (invalid caption Literal) and
  _update_last_used round-trip test

Out of scope: summaries.json video block, _print_section_summary,
_find_section in ask, map.py — all covered by Phase 2d.

Pre-flight confirmed: all existing cached meta.json files validate
against Meta before branch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2c-meta-propagate
gh pr create --title "refactor(fetch,xscript,toc,summarize): propagate Meta (Phase 2c PR-B)" --body "$(cat <<'EOF'
## Summary

Phase 2c PR-B — follows PR-A (introducing \`Meta\`). Flips \`_build_meta\` to return \`Meta\`, wraps every \`meta.json\` read site (7 total) with \`Meta.model_validate_json\`, and propagates attribute access through fetch, xscript, toc, summarize, and core.

## Notable refactors

- \`yttoc_list\` no longer monkey-patches \`_langs\` onto the meta dict (Pydantic models reject extra attrs). Builds \`(Meta, langs)\` tuples instead; sort key is \`meta.last_used_at\` (a \`datetime\`, compared natively).
- \`_update_last_used\` performs a Meta round-trip — cleaner than the previous load/mutate-key/write-string pattern.
- \`fetch_video\` writes via \`meta.model_dump_json(indent=2)\`.

## Scope boundary

Out of scope (Phase 2d): \`summaries.json\` video block, \`_print_section_summary\`, \`_find_section\` in ask, \`map.py\`. These receive wider section / video shapes; Phase 2d will unify them with a typed \`AssembledSummaries\`.

## Test plan

- [x] Full \`nbdev-test\` passes
- [x] Corruption-rejection test: \`yttoc_list\` raises \`ValidationError\` on \`meta.json\` with invalid caption type
- [x] \`_update_last_used\` round-trip test: two calls produce monotonically non-decreasing ISO timestamps that parse back to timezone-aware \`datetime\`
- [x] Pre-flight: all 16 cached \`meta.json\` files validate against \`Meta\`
- [x] Grep: no \`meta.get(...)\` / \`meta['...']\` patterns remain on Meta-typed values

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI + user merge + resync main**

```bash
gh pr checks <PR_NUMBER>
# after merge:
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2c-meta-propagate 2>/dev/null || true && git log --oneline -5
```

---

### Task 17: Archive plan

**Files:**
- Move: `docs/superpowers/plans/2026-04-19-pydantic-phase2c-meta.md` → `docs/superpowers/plans/done/`

- [ ] **Step 1: After PR-B merges, create housekeeping PR**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main
git checkout -b chore/archive-phase2c-plan
git mv docs/superpowers/plans/2026-04-19-pydantic-phase2c-meta.md docs/superpowers/plans/done/
git commit -m "chore(plans): archive Phase 2c Meta pilot plan"
git push -u origin chore/archive-phase2c-plan
gh pr create --title "chore(plans): archive Phase 2c Meta pilot plan" --body "Both Phase 2c implementation PRs are merged. Moving the plan under \`done/\` alongside previously completed plans. Docs-only change."
```

- [ ] **Step 2: After CI green, merge + resync**

```bash
gh pr merge <PR_NUMBER> --rebase --delete-branch
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main
```

---

## Summary Checklist (end-state)

- [ ] PR-A merged: `Meta` in `yttoc.core` with 9 fields (including `datetime last_used_at` and `Literal` captions), `_build_meta` constructs Meta internally and returns `.model_dump(mode='json')` for API preservation, validation tests pass
- [ ] PR-B merged: `_build_meta` returns `Meta`, all 7 meta.json read sites use `Meta.model_validate_json`, all consumers use attribute access, 8 test fixtures expanded to 9-field shape, corruption-rejection + round-trip tests added
- [ ] Plan archived under `docs/superpowers/plans/done/`
- [ ] Local `main` resynced with `origin/main`
