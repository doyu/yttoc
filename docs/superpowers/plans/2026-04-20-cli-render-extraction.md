# CLI Render Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract module-local `_render_*() -> str` helpers from the four CLI entrypoints (`yttoc_raw`, `yttoc_txt`, `yttoc_toc`, `yttoc_sum`), keeping CLI functions thin (load → render → print → side-effect). Output behavior unchanged.

**Architecture:** Single PR, three commits (one per touched module). Each CLI entrypoint becomes: load/compute data → call `_render_*()` → `print()` the returned string → side-effects (e.g. `_update_last_used`). No central `render.py`; helpers are strictly module-local. Existing stdout-capture CLI tests stay (behavior preservation); new direct render tests demonstrate the no-stdout-capture benefit.

**Tech Stack:** Python, nbdev 3, Pydantic v2. All `nbdev-*` commands run from `/home/doyu/yttoc/` under `.venv`.

**Spec:** GitHub issue #29 — "Extract CLI rendering into module-local render helpers."

**Execution environment:** Use `/home/doyu/yttoc/.venv/bin/python`, `/home/doyu/yttoc/.venv/bin/nbdev-export`, `/home/doyu/yttoc/.venv/bin/nbdev-test`. Edit notebooks by loading JSON with Python, mutating target cells' `source`, writing back, then running `scripts/normalize_notebooks.py`.

**AGENTS.md compliance:**
- Stage for review before every commit (`git diff --staged` shown to user).
- No direct push to `main`; PR lives on feature branch `refactor/cli-render-extraction`.
- 1 PR ≈ under 200 lines (this plan expects ~90 lines net).
- Target cell IDs are pinned in each task. If `nbdev-prepare` regenerates IDs, re-read them before editing.

---

## File Structure

### Touched files
- `nbs/02_xscript.ipynb` — replace CLI cell `bcd5731c`; add render tests after it
- `nbs/03_toc.ipynb` — replace CLI cell `795bea0d`; add render test after it
- `nbs/04_summarize.ipynb` — replace CLI cell `d286018a`; add render tests after it
- Generated `yttoc/xscript.py`, `yttoc/toc.py`, `yttoc/summarize.py`, `yttoc/_modidx.py`

### No new files
Per issue scope: no `render.py`. All helpers stay private (underscore-prefixed, not exported in `__all__`).

---

## Task 1: Create feature branch

**Files:** none

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: clean, up-to-date.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/cli-render-extraction
```

- [ ] **Step 3: Baseline green**

```bash
source .venv/bin/activate && nbdev-test
```

Expected: all tests pass. Record baseline count.

---

## Task 2: Extract `_render_raw` and `_render_txt` in `nbs/02_xscript.ipynb`

**Files:**
- Modify: `nbs/02_xscript.ipynb` cell `bcd5731c` (CLI cell)
- Modify: `nbs/02_xscript.ipynb` — insert new test cells after cell `53fd3bbe` (last yttoc_txt test)
- Generated: `yttoc/xscript.py`

### Step 1: Replace CLI cell `bcd5731c` with new source

- [ ] **Step 1a: Rewrite cell `bcd5731c`**

Use Python to load the notebook, locate the cell by id, replace `source` with the new content below, and write back. Keep the cell `id`, `cell_type`, and `metadata` unchanged.

New cell source (verbatim):

```python
#| export
import json
from fastcore.script import call_parse
from yttoc.core import fmt_duration, format_header, slice_segments, NormalizedSection, Meta
from yttoc.fetch import _DEFAULT_ROOT, _update_last_used, _glob_srt
from yttoc.toc import TocFile

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

    if section:
        toc_path = d / 'toc.json'
        if not toc_path.exists():
            raise SystemExit(f"No toc.json for {video_id}. Run yttoc-toc first.")
        toc = TocFile.model_validate_json(toc_path.read_text(encoding='utf-8'))
        sec_info = next((s for s in toc.sections if s.path == section), None)
        if sec_info is None:
            raise SystemExit(f"Section {section} not found")
        segments = slice_segments(segments, sec_info.start, sec_info.end)

    return meta, segments, sec_info, meta_path

def _render_raw(meta: Meta, # Parsed Meta instance
                segments: list[Segment], # Xscript segments (possibly sliced)
                section: str, # Section path (e.g. "3"); '' for full
                sec_info: NormalizedSection | None, # Matched section or None
               ) -> str: # Rendered multi-line transcript with timestamps
    "Render timestamped transcript output for yttoc_raw."
    lines = [format_header(meta), '']
    if sec_info is not None:
        s_start = fmt_duration(sec_info.start)
        s_end = fmt_duration(sec_info.end)
        lines.append(f"## {section}. {sec_info.title} ({s_start} - {s_end})")
    for s in segments:
        mm = int(s.start // 60)
        ss = int(s.start % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
    return '\n'.join(lines)

def _render_txt(meta: Meta, # Parsed Meta instance
                segments: list[Segment], # Xscript segments (possibly sliced)
                section: str, # Section path; '' for full
                sec_info: NormalizedSection | None, # Matched section or None
               ) -> str: # Rendered prose with no timestamps
    "Render plain-prose transcript output for yttoc_txt."
    lines = [format_header(meta), '']
    if sec_info is not None:
        s_start = fmt_duration(sec_info.start)
        s_end = fmt_duration(sec_info.end)
        lines.append(f"## {section}. {sec_info.title} ({s_start} - {s_end})")
        lines.append('')
    lines.append(' '.join(s.text for s in segments))
    return '\n'.join(lines)

@call_parse
def yttoc_raw(video_id: str, # Exact video_id
              section: str = '', # Section path (e.g. "3"); empty for full transcript
              root: str = None, # Root cache directory (default: ~/.cache/yttoc)
             ):
    "Display transcript for a cached video (full or by section)."
    meta, segments, sec_info, meta_path = _load_segments(video_id, section, root)
    print(_render_raw(meta, segments, section, sec_info))
    _update_last_used(meta_path)

@call_parse
def yttoc_txt(video_id: str, # Exact video_id
              section: str = '', # Section path (e.g. "3"); empty for full transcript
              root: str = None, # Root cache directory (default: ~/.cache/yttoc)
             ):
    "Display transcript as plain prose with no timestamps."
    meta, segments, sec_info, meta_path = _load_segments(video_id, section, root)
    print(_render_txt(meta, segments, section, sec_info))
    _update_last_used(meta_path)
```

Editing helper (run from repo root):

```bash
python - <<'PY'
import json, pathlib
p = pathlib.Path('nbs/02_xscript.ipynb')
nb = json.loads(p.read_text())
target_id = 'bcd5731c'
new_src = '''<paste NEW SOURCE above, as a single string>'''
for c in nb['cells']:
    if c.get('id') == target_id:
        c['source'] = new_src.splitlines(keepends=True)
        break
else:
    raise SystemExit(f'cell {target_id} not found')
p.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n')
PY
```

- [ ] **Step 1b: Normalize notebooks**

```bash
python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

### Step 2: Add new render-direct test cell

Insert a new code cell immediately after cell id `53fd3bbe`. Use a stable new cell id like `r1render01`.

- [ ] **Step 2a: Add cell `r1render01`**

New cell source (verbatim):

```python
# Test: _render_raw returns header + [MM:SS] lines with no stdout capture
from yttoc.xscript import _render_raw, _render_txt
from yttoc.core import Segment, Meta
from datetime import datetime, timezone

meta = Meta(id='VIDR', title='T', channel='C', duration=120, upload_date='20260101',
            webpage_url='https://youtube.com/watch?v=VIDR', description='',
            captions={'en': 'auto'},
            last_used_at=datetime(2026,1,1,tzinfo=timezone.utc))
segs = [Segment(start=65.0, end=68.0, text='hello world'),
        Segment(start=70.0, end=73.0, text='second line')]

out = _render_raw(meta, segs, '', None)
assert '# T' in out
assert '[01:05] hello world' in out
assert '[01:10] second line' in out
assert out.count('\n') == 3  # header, blank, two segment lines

# With section info
from yttoc.core import NormalizedSection
sec = NormalizedSection(path='2', title='Main', start=60, end=90)
out2 = _render_raw(meta, segs, '2', sec)
assert '## 2. Main (1:00 - 1:30)' in out2
print('ok')
```

- [ ] **Step 2b: Add cell `r1render02`**

New cell source (verbatim):

```python
# Test: _render_txt returns joined prose with no timestamps
from yttoc.xscript import _render_txt
from yttoc.core import Segment, Meta, NormalizedSection
from datetime import datetime, timezone

meta = Meta(id='VIDT', title='T2', channel='C2', duration=60, upload_date='20260101',
            webpage_url='', description='', captions={'en': 'auto'},
            last_used_at=datetime(2026,1,1,tzinfo=timezone.utc))
segs = [Segment(start=0.0, end=3.0, text='alpha beta'),
        Segment(start=3.0, end=6.0, text='gamma')]

out = _render_txt(meta, segs, '', None)
assert 'alpha beta gamma' in out
assert '[00:00]' not in out  # no timestamps

sec = NormalizedSection(path='1', title='Intro', start=0, end=30)
out2 = _render_txt(meta, segs, '1', sec)
assert '## 1. Intro (0:00 - 0:30)' in out2
assert 'alpha beta gamma' in out2
print('ok')
```

Editing helper: same Python pattern as Step 1a, but inserting new cell dicts after the one with id `53fd3bbe`. Each new cell:

```python
{"cell_type": "code", "execution_count": None, "id": "<new_id>",
 "metadata": {}, "outputs": [], "source": <list-of-lines>}
```

- [ ] **Step 2c: Normalize again**

```bash
python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

### Step 3: Regenerate module and test

- [ ] **Step 3a: Export**

```bash
nbdev-export
```

- [ ] **Step 3b: Confirm generated file matches expectation**

```bash
grep -n '_render_raw\|_render_txt\|yttoc_raw\|yttoc_txt' yttoc/xscript.py
```

Expected: both `_render_raw` and `_render_txt` defined; `yttoc_raw`/`yttoc_txt` call `print(_render_*(...))`.

- [ ] **Step 3c: Run tests**

```bash
nbdev-test
```

Expected: all tests green (including existing stdout-capture tests 9–13 and the two new render tests).

### Step 4: Commit

- [ ] **Step 4a: Stage and show diff to user**

```bash
git add nbs/02_xscript.ipynb yttoc/xscript.py yttoc/_modidx.py
git diff --staged --stat
```

- [ ] **Step 4b: Commit after user review**

```bash
git commit -m "$(cat <<'EOF'
refactor(xscript): extract _render_raw and _render_txt

Split transcript CLI entrypoints into thin load → render → print → side-effect
flow. Adds module-local render helpers returning strings; adds direct render
tests that do not require stdout capture. Behavior unchanged.

Refs #29

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Extract `_render_toc` in `nbs/03_toc.ipynb`

**Files:**
- Modify: `nbs/03_toc.ipynb` cell `795bea0d` (CLI cell)
- Modify: `nbs/03_toc.ipynb` — insert new test cell after cell `e5f6a7b8`
- Generated: `yttoc/toc.py`

### Step 1: Replace CLI cell `795bea0d`

- [ ] **Step 1a: Rewrite cell `795bea0d`**

New cell source (verbatim):

```python
#| export
import sys
from fastcore.script import call_parse
from yttoc.core import format_header, format_toc_line, Meta
from yttoc.fetch import _DEFAULT_ROOT, _update_last_used, _glob_srt
from yttoc.xscript import parse_xscript

def generate_toc(video_id: str, # Exact video_id
                 root: Path = None, # Root cache directory
                 refresh: bool = False, # Delete cached toc/summaries and regenerate
                ) -> list[NormalizedSection]: # List of NormalizedSection
    "Generate toc.json for a cached video. Returns sections list."
    root = root or _DEFAULT_ROOT
    d = root / video_id
    meta_path = d / 'meta.json'
    toc_path = d / 'toc.json'
    srt_files = _glob_srt(d)
    if not (meta_path.exists() and srt_files):
        raise SystemExit(f"Not cached: {video_id}")

    if refresh:
        if toc_path.exists(): toc_path.unlink()
        sum_path = d / 'summaries.json'
        if sum_path.exists():
            sum_path.unlink()
            print('Invalidated summaries.json (depends on toc)', file=sys.stderr)

    if toc_path.exists():
        return TocFile.model_validate_json(toc_path.read_text(encoding='utf-8')).sections

    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    segments = parse_xscript(srt_files[0])
    prompt = _build_toc_prompt(segments, meta)
    raw = _call_llm(prompt)
    sections = _normalize_sections(raw, meta.duration)

    toc_path.write_text(
        TocFile(sections=sections).model_dump_json(indent=2),
        encoding='utf-8')
    _update_last_used(meta_path)
    return sections

def _render_toc(meta: Meta, # Parsed Meta instance
                sections: list[NormalizedSection], # Normalized TOC sections
               ) -> str: # Rendered TOC: header + blank + formatted lines
    "Render TOC output for yttoc_toc."
    lines = [format_header(meta), '']
    url = meta.webpage_url
    for s in sections:
        lines.append(format_toc_line(s, url))
    return '\n'.join(lines)

@call_parse
def yttoc_toc(video_id: str, # Exact video_id
              root: str = None, # Root cache directory
              refresh: bool = False, # Regenerate toc (and invalidate summaries)
             ):
    "Generate and display Table of Contents for a cached video."
    root = Path(root) if root else _DEFAULT_ROOT
    d = root / video_id
    meta_path = d / 'meta.json'
    if not meta_path.exists():
        raise SystemExit(f"Not cached: {video_id}")

    meta = Meta.model_validate_json(meta_path.read_text(encoding='utf-8'))
    sections = generate_toc(video_id, root, refresh=refresh)
    print(_render_toc(meta, sections))
```

- [ ] **Step 1b: Normalize**

```bash
python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

### Step 2: Add render-direct test cell

Insert a new code cell after cell id `e5f6a7b8`. New cell id: `r2render01`.

- [ ] **Step 2a: Add cell `r2render01`**

New cell source (verbatim):

```python
# Test: _render_toc returns header + blank + formatted section lines
from yttoc.toc import _render_toc
from yttoc.core import NormalizedSection, Meta
from datetime import datetime, timezone

meta = Meta(id='VID2', title='Test Video', channel='Ch', duration=900,
            upload_date='20260101', webpage_url='https://youtube.com/watch?v=VID2',
            description='', captions={'en': 'auto'},
            last_used_at=datetime(2000,1,1,tzinfo=timezone.utc))
sections = [NormalizedSection(path='1', title='Intro', start=0, end=300),
            NormalizedSection(path='2', title='Main', start=300, end=900)]

out = _render_toc(meta, sections)
lines = out.split('\n')
assert '# Test Video' in lines[0]
assert lines[1] == ''
assert '1. Intro 0:00-5:00' in out
assert '2. Main 5:00-15:00' in out
assert '&t=300' in out
print('ok')
```

- [ ] **Step 2b: Normalize**

```bash
python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

### Step 3: Regenerate and test

- [ ] **Step 3a: Export**

```bash
nbdev-export
```

- [ ] **Step 3b: Verify**

```bash
grep -n '_render_toc\|yttoc_toc' yttoc/toc.py
```

Expected: `_render_toc` defined; `yttoc_toc` calls `print(_render_toc(meta, sections))`.

- [ ] **Step 3c: Run tests**

```bash
nbdev-test
```

Expected: green.

### Step 4: Commit

- [ ] **Step 4a: Stage and show diff**

```bash
git add nbs/03_toc.ipynb yttoc/toc.py yttoc/_modidx.py
git diff --staged --stat
```

- [ ] **Step 4b: Commit after review**

```bash
git commit -m "$(cat <<'EOF'
refactor(toc): extract _render_toc

Split yttoc_toc into thin load → generate → render → print flow with a
module-local _render_toc helper; adds direct render test. Behavior unchanged.

Refs #29

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Extract `_render_summaries` in `nbs/04_summarize.ipynb`

**Files:**
- Modify: `nbs/04_summarize.ipynb` cell `d286018a` (CLI cell)
- Modify: `nbs/04_summarize.ipynb` — insert new test cell after cell `fbf6535c`
- Generated: `yttoc/summarize.py`

### Step 1: Replace CLI cell `d286018a`

Replaces `_print_section_summary` with a pure `_format_section_summary(s, url) -> list[str]`, adds `_render_summaries(sums, section) -> str` that raises `ValueError` on missing section. `yttoc_sum` catches the error and re-raises as `SystemExit` to preserve current behavior.

- [ ] **Step 1a: Rewrite cell `d286018a`**

New cell source (verbatim):

```python
#| export
from fastcore.script import call_parse
from yttoc.core import fmt_duration, format_header, format_toc_line, NormalizedSection, Meta
from yttoc.fetch import _DEFAULT_ROOT, _update_last_used, _glob_srt
from yttoc.xscript import parse_xscript
from yttoc.toc import generate_toc

def _assemble_summaries(meta: Meta, # Parsed Meta instance
                        toc_sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                        llm_result: dict # {full, sections: {path: {...}}}
                       ) -> AssembledSummaries: # Parsed AssembledSummaries instance
    "Merge meta + toc + LLM output into the canonical summaries.json shape. Raise if LLM omitted any section."
    missing = [sec.path for sec in toc_sections if sec.path not in llm_result['sections']]
    if missing:
        raise ValueError(f"LLM omitted summaries for sections: {missing}")
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

def _format_section_summary(s: AssembledSection, # Assembled section with summary payload
                            url: str, # Canonical video URL ('' when absent)
                           ) -> list[str]: # Four-line block: TOC heading, summary, keywords, evidence
    "Format one section as a TOC-heading block."
    return [
        f"## {format_toc_line(s, url)}",
        s.summary,
        f"**Keywords:** {', '.join(s.keywords)}",
        f"**Evidence:** \"{s.evidence.text}\" [{fmt_duration(s.evidence.at)}]",
    ]

def _render_summaries(sums: AssembledSummaries, # Parsed summaries.json
                     section: str = '', # Section path; '' for all sections + full summary
                    ) -> str: # Rendered summaries output
    "Render summary output for yttoc_sum. Raise ValueError if section missing."
    url = sums.video.url or ''
    lines = [format_header(sums.video), '']
    if section:
        s = next((sec for sec in sums.sections if sec.path == section), None)
        if s is None:
            raise ValueError(f"Section {section} not found")
        lines.extend(_format_section_summary(s, url))
    else:
        for s in sums.sections:
            lines.extend(_format_section_summary(s, url))
            lines.append('')
        lines.append("## Full Summary")
        lines.append(sums.full.summary)
        lines.append(f"**Keywords:** {', '.join(sums.full.keywords)}")
        lines.append(f"**Evidence:** \"{sums.full.evidence.text}\" [{fmt_duration(sums.full.evidence.at)}]")
        if url: lines.append(url)
    return '\n'.join(lines)

@call_parse
def yttoc_sum(video_id: str, # Exact video_id
              section: str = '', # Section path (e.g. "3"); empty for all
              root: str = None, # Root cache directory
              refresh: bool = False, # Regenerate summaries
             ):
    "Display summaries for a cached video."
    root = Path(root) if root else _DEFAULT_ROOT
    sums = generate_summaries(video_id, root, refresh=refresh)
    try:
        print(_render_summaries(sums, section))
    except ValueError as e:
        raise SystemExit(str(e))
```

Verify output equivalence: the previous code printed each per-section block with 4 lines + a trailing blank `print()`, then `## Full Summary` and four more lines, then an optional url line. The new flow joins `lines` with `\n` and prints once, which emits the same characters + one trailing newline (from `print`). Trailing blank-after-last-section becomes an empty element in `lines` → renders as an extra `\n` before `## Full Summary`, matching the prior output.

- [ ] **Step 1b: Normalize**

```bash
python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

### Step 2: Add render-direct test cells

Insert new cells after cell id `fbf6535c`. New ids: `r3render01`, `r3render02`.

- [ ] **Step 2a: Add cell `r3render01`**

New cell source (verbatim):

```python
# Test: _render_summaries (all sections + full) returns expected block
from yttoc.summarize import _render_summaries

sums_dict = _make_test_summaries('VID9', url='https://youtube.com/watch?v=VID9')
sums_dict['video']['title'] = 'Test Video'
sums_dict['video']['channel'] = 'Ch'
sums = AssembledSummaries.model_validate(sums_dict)

out = _render_summaries(sums, '')
assert '# Test Video' in out
assert '## 1. Intro' in out
assert '## 2. Main' in out
assert '## Full Summary' in out
assert 'Full video about testing.' in out
assert out.endswith('https://youtube.com/watch?v=VID9')  # url footer
print('ok')
```

- [ ] **Step 2b: Add cell `r3render02`**

New cell source (verbatim):

```python
# Test: _render_summaries(section='2') returns one section; missing section raises ValueError
from yttoc.summarize import _render_summaries

sums = AssembledSummaries.model_validate(_make_test_summaries('VIDX'))

out = _render_summaries(sums, '2')
assert '## 2. Main' in out
assert '## 1. Intro' not in out
assert '## Full Summary' not in out

try:
    _render_summaries(sums, '99')
except ValueError as e:
    assert 'Section 99 not found' in str(e)
else:
    raise AssertionError('expected ValueError for missing section')
print('ok')
```

- [ ] **Step 2c: Normalize**

```bash
python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

### Step 3: Regenerate and test

- [ ] **Step 3a: Export**

```bash
nbdev-export
```

- [ ] **Step 3b: Verify**

```bash
grep -n '_render_summaries\|_format_section_summary\|yttoc_sum' yttoc/summarize.py
```

Expected: `_format_section_summary` and `_render_summaries` defined; `_print_section_summary` removed; `yttoc_sum` calls `_render_summaries` inside try/except.

- [ ] **Step 3c: Run tests**

```bash
nbdev-test
```

Expected: green — Tests 5 (all-sections) and 6 (--section) still pass (behavior preserved); two new render tests also pass.

### Step 4: Commit

- [ ] **Step 4a: Stage and show diff**

```bash
git add nbs/04_summarize.ipynb yttoc/summarize.py yttoc/_modidx.py
git diff --staged --stat
```

- [ ] **Step 4b: Commit after review**

```bash
git commit -m "$(cat <<'EOF'
refactor(summarize): extract _render_summaries

Split yttoc_sum into thin generate → render → print flow. Replaces
_print_section_summary with pure _format_section_summary(list[str]) and
_render_summaries(sums, section) -> str. Missing sections raise
ValueError, caught in CLI to preserve SystemExit behavior.

Refs #29

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Open PR

**Files:** none

- [ ] **Step 1: Push branch**

```bash
git push -u origin refactor/cli-render-extraction
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "refactor: extract CLI render helpers (closes #29)" --body "$(cat <<'EOF'
## Summary
- Add module-local `_render_raw` / `_render_txt` in `xscript.py`
- Add `_render_toc` in `toc.py`
- Add `_render_summaries` + `_format_section_summary` in `summarize.py` (replaces `_print_section_summary`)
- CLI entrypoints become: load → render → print → side-effect
- Output behavior unchanged; existing stdout-capture tests still green; direct render tests added

Closes #29

## Test plan
- [x] `nbdev-test` green
- [x] Existing CLI stdout-capture tests pass (behavior preserved)
- [x] New `_render_*` tests pass without stdout capture

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

- [x] **Spec coverage:** Each CLI in issue #29 (`yttoc_raw`, `yttoc_txt`, `yttoc_toc`, `yttoc_sum`) has a render helper (Tasks 2–4). No central `render.py`. `core.py` formatters (`fmt_duration`, `format_header`, `format_toc_line`) reused — not duplicated.
- [x] **No placeholders:** Every new cell body and every grep/command is literal. Cell IDs are explicit.
- [x] **Type consistency:** `_render_raw(meta, segments, section, sec_info)`, `_render_txt(meta, segments, section, sec_info)`, `_render_toc(meta, sections)`, `_render_summaries(sums, section='')` — signatures match across plan and tests.
- [x] **Behavior preservation:** Output-equivalence reasoning included for each CLI (trailing-newline from `print()` matches prior per-line `print()` output).
- [x] **Error paths:** `yttoc_sum` preserves `SystemExit("Section X not found")` by catching `ValueError` from `_render_summaries`.
