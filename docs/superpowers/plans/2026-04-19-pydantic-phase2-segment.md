# Pydantic Phase 2 — Segment Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate Pydantic typing through the internal xscript-segment pipeline by introducing a `Segment` BaseModel in `core`, switching `parse_xscript` to return `list[Segment]`, and updating all consumers to attribute access. Split into two PRs to stay under the 200-line guideline and isolate risk.

**Architecture:** `Segment` lives in `nbs/00_core.ipynb` (not `nbs/02_xscript.ipynb`) because `xscript` already imports from `core`; placing `Segment` in `xscript` would create a circular import. PR #1 introduces the model and uses it internally in `parse_xscript` while preserving the `list[dict]` public return, so no consumers break. PR #2 flips the return type to `list[Segment]` and updates every consumer — a cross-module atomic refactor that intentionally leaves intermediate states with failing tests; only the full test suite at the end of PR #2 confirms success.

**Tech Stack:** Python, nbdev 3, Pydantic v2, OpenAI Chat Completions API (unchanged). All `nbdev-*` commands run under `/home/doyu/yttoc/.venv`.

**Spec:** `docs/superpowers/specs/2026-04-19-pydantic-phase2-segment-design.md` (commit `5c03e4b`).

**Execution environment:** Run all commands from `/home/doyu/yttoc/`. Use `/home/doyu/yttoc/.venv/bin/` binaries directly (no need to `source activate`).

**AGENTS.md compliance checkpoints:**
- Stage for review (`git diff --cached`) before every commit.
- No direct push to `main`; each PR lives on a feature branch.
- One feature per PR. Rebase-merge on GitHub; delete branch after merge; `git reset --hard origin/main` locally to resync.

---

## File Structure

### PR #1 — touches
- `nbs/00_core.ipynb` — add `Segment` BaseModel + validation test
- `nbs/02_xscript.ipynb` — import `Segment`, use inside `parse_xscript`
- `yttoc/core.py`, `yttoc/xscript.py` — regenerated via `nbdev-export`
- `yttoc/_modidx.py` — regenerated (new `Segment` entry)

### PR #2 — touches
- `nbs/00_core.ipynb` — retype `slice_segments`
- `nbs/02_xscript.ipynb` — flip `parse_xscript` return + update CLI display + update `get_xscript_range` body + rewrite 21 subscript assertions in Tests 1-7 and Test 14
- `nbs/03_toc.ipynb` — update `_build_toc_prompt` body + rewrite Test 6 fixture (2 dict literals → `Segment(...)`)
- `nbs/04_summarize.ipynb` — update `_build_summary_prompt` body + rewrite Test 1 fixture (4 literals) and Test 3 fixture (2 literals)
- `nbs/06_ask.ipynb` — add `_to_jsonable` helper inside `dispatch_tool` + add unit test + add boundary contract test
- Generated `yttoc/*.py` — regenerated via `nbdev-export`

---

## PR #1 — Introduce `Segment` in core (internal use only)

Public API unchanged: `parse_xscript` still returns `list[dict]`. Zero consumer impact.

### Task 1: Create PR #1 feature branch

**Files:** none

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: `On branch main`, `nothing to commit, working tree clean`, local HEAD matches `origin/main`.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2-segment-intro
```

Expected: `Switched to a new branch 'refactor/pydantic-phase2-segment-intro'`.

---

### Task 2: Add `Segment` model to `nbs/00_core.ipynb`

`core` currently has no Pydantic imports. This task adds them together with the `Segment` class. A separate validation test is added in Task 3.

**Files:**
- Modify: `nbs/00_core.ipynb` — cell `ec3460e1` (the large `#| export` cell with `fmt_duration`, `format_header`, `slice_segments`)

- [ ] **Step 1: Read the current content of cell `ec3460e1`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/00_core.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'ec3460e1':
        print(''.join(c['source']))
"
```

Expected: code containing `def fmt_duration(...)`, `def format_header(...)`, `def format_toc_line(...)`, `def slice_segments(...)`. Does not contain `Segment` or `pydantic`.

- [ ] **Step 2: Edit cell `ec3460e1` — add `pydantic` import and `Segment` class**

Open `nbs/00_core.ipynb` in Jupyter/VS Code and edit cell `ec3460e1`. Add at the top of the cell (right after `#| export`):

```python
from pydantic import BaseModel, Field

class Segment(BaseModel):
    "One parsed xscript segment (in-memory)."
    start: float = Field(ge=0, description="Start time in seconds")
    end: float = Field(ge=0, description="End time in seconds")
    text: str = Field(description="Normalized cue text")
```

Leave the existing `fmt_duration`, `format_header`, `format_toc_line`, `slice_segments` definitions unchanged. Do NOT retype `slice_segments` yet — that happens in PR #2.

- [ ] **Step 3: Normalize + export**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb && .venv/bin/nbdev-export
```

Expected: `normalized: nbs/00_core.ipynb`, and no errors from `nbdev-export`.

- [ ] **Step 4: Verify `Segment` landed in generated module**

```bash
/home/doyu/yttoc/.venv/bin/python -c "from yttoc.core import Segment; s = Segment(start=1.0, end=2.0, text='hi'); print(s)"
```

Expected: `start=1.0 end=2.0 text='hi'` (Pydantic v2 repr).

---

### Task 3: Add `Segment` validation test in `nbs/00_core.ipynb`

**Files:**
- Modify: `nbs/00_core.ipynb` — add a new test cell immediately after cell `9fb67fec` (the `format_toc_line` test)

- [ ] **Step 1: Add new test cell**

In Jupyter/VS Code, insert a new **code cell** after cell `9fb67fec` with this content:

```python
# Test: Segment validates non-negative timestamps
from yttoc.core import Segment
from pydantic import ValidationError

# Valid construction succeeds
s = Segment(start=0.0, end=1.5, text='x')
assert s.start == 0.0 and s.end == 1.5 and s.text == 'x'

# Negative start rejected
try:
    Segment(start=-0.001, end=0.0, text='x')
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative start'

# Negative end rejected
try:
    Segment(start=0.0, end=-1, text='x')
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative end'

print('ok')
```

- [ ] **Step 2: Normalize and run the notebook's tests**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb && .venv/bin/nbdev-test --path nbs/00_core.ipynb
```

Expected: `Success.`

---

### Task 4: Use `Segment` internally in `parse_xscript` (`nbs/02_xscript.ipynb`)

Public signature stays `list[dict]`. Internal construction uses `Segment(...)`, then `.model_dump()` on return.

**Files:**
- Modify: `nbs/02_xscript.ipynb`
  - cell `a1000004` — the module-top imports cell
  - cell `a1000006` — the large `#| export` cell containing `_parse_srt`, `_normalize_cue`, `parse_xscript`

- [ ] **Step 1: Inspect current state of target cells**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/02_xscript.ipynb'))
for c in nb['cells']:
    if c.get('id') in ('a1000004','a1000006'):
        print(f'=== {c[\"id\"]} ===')
        print(''.join(c['source']))
        print()
"
```

Expected: `a1000004` contains `import re` and `from pathlib import Path`; `a1000006` contains `parse_xscript` returning a plain list of dicts.

- [ ] **Step 2: Edit cell `a1000004` — import `Segment`**

Edit cell `a1000004` to add the import at the bottom:

```python
#| export
import re
from pathlib import Path
from yttoc.core import Segment
```

- [ ] **Step 3: Edit cell `a1000006` — minimal change to `parse_xscript` body**

In cell `a1000006`, find the `parse_xscript` function. Apply exactly two edits (do NOT rewrite the control flow — overlap detection and end clamping logic must stay bit-identical):

**Edit A**: Find the dict-literal append (around the bottom of the loop body):

```python
        if curr_tokens:
            segments.append({
                'start': start,
                'end': end,
                'text': ' '.join(curr_tokens),
            })
```

Replace with:

```python
        if curr_tokens:
            segments.append(Segment(start=start, end=end, text=' '.join(curr_tokens)))
```

**Edit B**: Find the final return statement:

```python
    return segments
```

Replace with:

```python
    return [s.model_dump() for s in segments]
```

Leave the function's signature `parse_xscript(path) -> list[dict]` unchanged. Leave the docstring unchanged. Leave `_parse_srt`, `_normalize_cue`, `_find_overlap`, and the overlap/clamp logic in the loop body untouched.

- [ ] **Step 4: Normalize + export**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb && .venv/bin/nbdev-export
```

Expected: `normalized: nbs/02_xscript.ipynb`, no export errors.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test
```

Expected: `Success.` — all notebooks pass because the public contract of `parse_xscript` is unchanged.

---

### Task 5: Stage PR #1 changes and request review

**Files:** staging only.

- [ ] **Step 1: Stage relevant files**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/02_xscript.ipynb yttoc/core.py yttoc/xscript.py yttoc/_modidx.py
```

- [ ] **Step 2: Show the cached diff for user review**

```bash
git status && git diff --cached --stat && git diff --cached
```

Expected: 5 files modified. `yttoc/core.py` gains `Segment` class and `pydantic` import. `yttoc/xscript.py` `parse_xscript` body constructs `Segment(...)` and returns `[s.model_dump() for s in segments]`.

- [ ] **Step 3: Pause for user review**

Per AGENTS.md, do not commit until the user has reviewed the staged diff. Ask: "PR #1 staged diff ready. Approve to commit, or indicate changes?"

---

### Task 6: Commit PR #1, push, and open GitHub PR

**Files:** none (git ops only).

- [ ] **Step 1: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(core,xscript): introduce Segment BaseModel in core

Define Segment Pydantic model in core (not xscript, to avoid the
circular import given that xscript imports slice_segments from core).
parse_xscript now constructs Segment objects internally and returns
list[dict] via model_dump, keeping the public contract unchanged.

This is Phase 2 pilot PR #1 of 2; PR #2 will flip parse_xscript to
return list[Segment] and propagate the type through all consumers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit created on `refactor/pydantic-phase2-segment-intro`.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2-segment-intro
gh pr create --title "refactor(core,xscript): introduce Segment BaseModel (Phase 2 pilot PR #1)" --body "$(cat <<'EOF'
## Summary

Phase 2 pilot PR #1 — introduces `Segment` Pydantic model in `nbs/00_core.ipynb` and uses it internally inside `parse_xscript`. Public return shape of `parse_xscript` stays `list[dict]` via `model_dump`; no consumer is affected. PR #2 (follow-up) will flip the return type and propagate through the pipeline.

Ownership rationale: `Segment` lives in `core` because `xscript` already imports `slice_segments` from `core`; placing `Segment` in `xscript` would create a circular import. See spec `docs/superpowers/specs/2026-04-19-pydantic-phase2-segment-design.md`.

## Test plan

- [x] `nbdev-test` full suite passes (public contract unchanged)
- [x] New test: `Segment(start=-1, end=0, text='x')` raises `ValidationError`
- [x] `from yttoc.core import Segment` works

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 3: Wait for CI + user merge**

Monitor:
```bash
gh pr checks <PR_NUMBER>
```

Stop here. Do NOT proceed to PR #2 until user merges PR #1 and confirms local `main` is resynced.

- [ ] **Step 4: After merge, resync local main**

```bash
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2-segment-intro 2>/dev/null || true && git log --oneline -3
```

Expected: local `main` matches `origin/main`; the PR's commit visible as the tip.

---

## PR #2 — Propagate `Segment` through the pipeline

**⚠ Atomic refactor note:** PR #2 changes `parse_xscript`'s return type and every consumer in lock-step. Between Task 8 and Task 14 below, the codebase is intentionally in a half-migrated state; `nbdev-test` will fail mid-PR. **Do not run the full test suite between Task 8 and Task 13.** The final green signal is Task 14.

If a later task reveals a design issue, do not try to "fix" the intermediate state — revert the branch and re-start the PR on a clean main.

---

### Task 7: Create PR #2 feature branch

**Files:** none.

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: clean tree, up-to-date with origin.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2-segment-propagate
```

---

### Task 8: Flip `parse_xscript` return to `list[Segment]`

**Files:**
- Modify: `nbs/02_xscript.ipynb` — cell `a1000006` (the `parse_xscript` export cell)

- [ ] **Step 1: Edit cell `a1000006`**

Apply exactly three small edits in the `parse_xscript` function:

1. Return annotation: `list[dict]` → `list[Segment]`
2. Inline signature comment: `List of {start, end, text} segments` → `List of Segment objects`
3. Final statement: `return [s.model_dump() for s in segments]` → `return segments`

All other lines (docstring, overlap/clamp logic, loop body) stay unchanged from PR #1.

- [ ] **Step 2: Normalize (do NOT run tests yet)**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

---

### Task 9: Migrate `nbs/02_xscript.ipynb` subscript assertions to attribute access

Tests 1-7 assert `segs[i]['key']`; Test 14 asserts `result[i]['key']`. All must become `.key` attribute access.

**Files:**
- Modify: `nbs/02_xscript.ipynb` — cells `a1000009`, `a1000010`, `a1000011`, `a1000012`, `a1000013`, `a806b72b`, `40c07205`, `0d9b3892`

- [ ] **Step 1: Rewrite Test 1 (cell `a1000009`)**

Find lines that assert `segs[0]['start']`, `segs[0]['end']`, `segs[0]['text']`. Rewrite:

```python
assert segs[0].start == 0.08
assert segs[0].end == 4.88
assert segs[0].text == 'hello world'
```

- [ ] **Step 2: Rewrite Test 2 (cell `a1000010`)**

```python
assert segs[0].text == 'first line second line'
```

- [ ] **Step 3: Rewrite Test 3 (cell `a1000011`)**

```python
assert segs[0].text == "code's not even the right verb anymore"
assert segs[1].text == 'to my agents'
assert segs[1].start == 5.0
```

- [ ] **Step 4: Rewrite Test 4 (cell `a1000012`)**

```python
assert segs[0].text == 'first sentence'
assert segs[1].text == 'completely different'
assert segs[1].start == 5.0
```

- [ ] **Step 5: Rewrite Test 5 (cell `a1000013`)**

```python
assert segs[0].text == 'hello world'
```

- [ ] **Step 6: Rewrite Test 6 (cell `a806b72b`)**

```python
assert segs[0].text == 'hello'
assert segs[1].text == 'world'
assert segs[1].start == 10.0
assert segs[1].end == 10.0
assert segs[1].start <= segs[1].end
```

- [ ] **Step 7: Rewrite Test 7 (cell `40c07205`)**

```python
assert segs[0].text == 'Here we go. Hello everybody.'
assert segs[1].text == 'next cue'
```

Test 8 (cell `b4e5c1e7`) — no changes (it only asserts `ValueError`, no subscript access).

- [ ] **Step 8: Rewrite Test 14 (cell `0d9b3892`)**

```python
result = get_xscript_range('VID_GXR', 5, 15, root)
assert isinstance(result, list)
assert len(result) == 2
assert result[0].text == 'second'
assert result[1].text == 'third'
assert isinstance(result[0].start, float)
assert isinstance(result[0].end, float)
# Verify the Segment fields are present as attributes (replaces the former dict-key presence check)
assert hasattr(result[0], 'start') and hasattr(result[0], 'end') and hasattr(result[0], 'text')
```

Tests 15 (`369fffc8`, error-dict branch) and 16 (`9ffc1b4f`, empty-list branch) — no changes.

- [ ] **Step 9: Normalize (do NOT run tests yet — `slice_segments` / CLI still subscript)**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

---

### Task 10: Update `yttoc_raw`, `yttoc_txt`, `_load_segments`, `get_xscript_range` to attribute access

**Files:**
- Modify: `nbs/02_xscript.ipynb`
  - cell `bcd5731c` — contains `_load_segments`, `yttoc_raw`, and `yttoc_txt` (all three in one cell)
  - cell `db2334f5` — contains `get_xscript_range` only

- [ ] **Step 1: In cell `bcd5731c`, update the `_load_segments` return annotation and the `yttoc_raw` / `yttoc_txt` display loops**

First, update the `_load_segments` signature — the second tuple element changes from `list[dict]` to `list[Segment]`:

```python
def _load_segments(video_id: str, section: str, root: str | None
                  ) -> tuple[dict, list[Segment], dict | None, Path]:
    ...
```

Add `from yttoc.core import Segment` at the top of the cell (right after `#| export`) if not already present (check the imports — `slice_segments` is already imported from `yttoc.core`, so just add `Segment` to that line or a new import).

Then, inside `yttoc_raw`, replace:
```python
for s in segments:
    mm = int(s['start'] // 60)
    ss = int(s['start'] % 60)
    print(f"[{mm:02d}:{ss:02d}] {s['text']}")
```
with:
```python
for s in segments:
    mm = int(s.start // 60)
    ss = int(s.start % 60)
    print(f"[{mm:02d}:{ss:02d}] {s.text}")
```

Inside `yttoc_txt`, replace:
```python
print(' '.join(s['text'] for s in segments))
```
with:
```python
print(' '.join(s.text for s in segments))
```

Note: `_load_segments` body uses `sec_info['start']` / `sec_info['end']` — these are TOC sections, NOT xscript segments. Leave them as dict access (out of scope).

- [ ] **Step 2: In cell `db2334f5`, update `get_xscript_range` return annotation only**

The body needs no change — it just calls `parse_xscript` then `slice_segments`, both of which now return `list[Segment]` transitively. Only the signature needs updating:

```python
def get_xscript_range(video_id: str, # Exact video_id
                      start: int | float, # Start time in seconds
                      end: int | float, # End time in seconds
                      root: str | Path = None # Root cache directory
                     ) -> list[Segment] | dict: # List of Segment or {"error": "..."}
    ...
```

Also update the docstring's data-shape comment if it names `[{start, end, text}, ...]` — change to `list of Segment` or remove. Add `from yttoc.core import Segment` at the top of the cell if not already present.

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

---

### Task 11: Retype `slice_segments` in `nbs/00_core.ipynb`

**Files:**
- Modify: `nbs/00_core.ipynb` — cell `ec3460e1`

- [ ] **Step 1: Edit `slice_segments`**

Find:
```python
def slice_segments(segments: list[dict], # [{start, end, text}, ...]
                   start: int, # Section start in seconds
                   end: int # Section end in seconds
                  ) -> list[dict]: # Segments within [start, end)
    "Return segments with start time inside [start, end)."
    return [s for s in segments if s['start'] >= start and s['start'] < end]
```

Replace with:
```python
def slice_segments(segments: list[Segment], # List of Segment
                   start: int, # Section start in seconds
                   end: int # Section end in seconds
                  ) -> list[Segment]: # Segments within [start, end)
    "Return segments with start time inside [start, end)."
    return [s for s in segments if s.start >= start and s.start < end]
```

`Segment` is already defined in the same cell (added in PR #1), so no import change needed.

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb
```

---

### Task 12: Update `_build_toc_prompt` and Test 6 fixture in `nbs/03_toc.ipynb`

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `d95b70ae` (`_build_toc_prompt` definition) and `2b1e3214` (Test 6)

- [ ] **Step 1: Edit cell `d95b70ae` — `_build_toc_prompt` loop**

Find:
```python
for s in segments:
    mm = int(s['start'] // 60)
    ss = int(s['start'] % 60)
    lines.append(f"[{mm:02d}:{ss:02d}] {s['text']}")
```

Replace with:
```python
for s in segments:
    mm = int(s.start // 60)
    ss = int(s.start % 60)
    lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
```

Also update the type annotation on the `segments` parameter:
```python
def _build_toc_prompt(segments: list[Segment], # List of xscript Segment
                      meta: dict # meta.json content
                     ) -> str: # Prompt for LLM
```

Add `from yttoc.core import Segment` at the top of the cell (right after `#| export`) if not already present. Check first by inspecting the cell.

- [ ] **Step 2: Edit cell `2b1e3214` — Test 6 fixture**

Find:
```python
segments = [
    {'start': 0.0, 'end': 5.0, 'text': 'hello world'},
    {'start': 5.0, 'end': 10.0, 'text': 'second segment'},
]
```

Replace with:
```python
from yttoc.core import Segment
segments = [
    Segment(start=0.0, end=5.0, text='hello world'),
    Segment(start=5.0, end=10.0, text='second segment'),
]
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

---

### Task 13: Update `_build_summary_prompt`, Test 1, Test 3 fixtures in `nbs/04_summarize.ipynb`

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cells `c1000005` (`_build_summary_prompt` definition), `c1000007` (Test 1), `c1000009` (Test 3)

- [ ] **Step 1: Edit cell `c1000005` — `_build_summary_prompt` loop**

Find:
```python
for sec in sections:
    sliced = slice_segments(segments, sec['start'], sec['end'])
    lines = []
    for s in sliced:
        mm = int(s['start'] // 60)
        ss = int(s['start'] % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s['text']}")
```

Replace the inner loop's subscripts:
```python
for sec in sections:
    sliced = slice_segments(segments, sec['start'], sec['end'])
    lines = []
    for s in sliced:
        mm = int(s.start // 60)
        ss = int(s.start % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
```

(The outer `sec['start']` / `sec['end']` are TOC sections — out of scope for this PR; leave them as dict access.)

Update `_build_summary_prompt` param annotation:
```python
def _build_summary_prompt(segments: list[Segment], # Full xscript segments
                          sections: list[dict], # [{path, title, start, end}, ...] from toc.json
                          meta: dict # meta.json content
                         ) -> str: # Prompt for LLM
```

Add `from yttoc.core import Segment` at the top of the cell if not already present.

- [ ] **Step 2: Edit cell `c1000007` — Test 1 fixture**

Find:
```python
segs = [
    {'start': 0, 'end': 5, 'text': 'a'},
    {'start': 5, 'end': 10, 'text': 'b'},
    {'start': 10, 'end': 15, 'text': 'c'},
    {'start': 15, 'end': 20, 'text': 'd'},
]
sliced = slice_segments(segs, start=5, end=15)
assert len(sliced) == 2
assert sliced[0]['text'] == 'b'
assert sliced[1]['text'] == 'c'
```

Replace with:
```python
from yttoc.core import Segment
segs = [
    Segment(start=0, end=5, text='a'),
    Segment(start=5, end=10, text='b'),
    Segment(start=10, end=15, text='c'),
    Segment(start=15, end=20, text='d'),
]
sliced = slice_segments(segs, start=5, end=15)
assert len(sliced) == 2
assert sliced[0].text == 'b'
assert sliced[1].text == 'c'
```

- [ ] **Step 3: Verify Test 2 (cell `c1000008`) still works with scope-shared `segs`**

Inspect cell `c1000008`:

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/04_summarize.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'c1000008':
        print(''.join(c['source']))
"
```

Expected content:
```python
# Test 2: slice_segments with no matching segments returns empty
sliced = slice_segments(segs, start=100, end=200)
assert sliced == []
```

No changes needed — `sliced == []` still holds; the shared `segs` is now `list[Segment]`.

- [ ] **Step 4: Edit cell `c1000009` — Test 3 fixture**

Find:
```python
segments = [
    {'start': 0, 'end': 5, 'text': 'hello world'},
    {'start': 5, 'end': 10, 'text': 'second part'},
]
```

Replace with:
```python
from yttoc.core import Segment
segments = [
    Segment(start=0, end=5, text='hello world'),
    Segment(start=5, end=10, text='second part'),
]
```

(The surrounding `sections = [...]` dicts are TOC sections — leave as-is.)

- [ ] **Step 5: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 14: Add `_to_jsonable` helper inside `dispatch_tool` (`nbs/06_ask.ipynb`)

**Files:**
- Modify: `nbs/06_ask.ipynb` — cell `b57a20ff` (the `dispatch_tool` export cell)

- [ ] **Step 1: Inspect current `dispatch_tool`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/06_ask.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'b57a20ff':
        print(''.join(c['source']))
"
```

- [ ] **Step 2: Edit cell `b57a20ff` — add `_to_jsonable` and apply it**

Inside the same cell, immediately before the `def dispatch_tool(...)` definition, insert:

```python
def _to_jsonable(o):
    "Recursively convert Pydantic BaseModel instances to dicts for JSON serialization."
    if isinstance(o, BaseModel): return o.model_dump()
    if isinstance(o, list): return [_to_jsonable(x) for x in o]
    if isinstance(o, dict): return {k: _to_jsonable(v) for k, v in o.items()}
    return o
```

Then modify the current `dispatch_tool` so that its success-path `json.dumps(result, ...)` wraps `result` via `_to_jsonable(result)` first:

```python
def dispatch_tool(registry: dict[str, ToolEntry], name: str, raw_args: str) -> str:
    "Validate args via Pydantic, call handler, return JSON result."
    tool = registry.get(name)
    if tool is None:
        return json.dumps({'error': f'Unknown tool: {name}'}, ensure_ascii=False)
    try:
        args = tool.args_model.model_validate_json(raw_args)
        result = tool.handler(**args.model_dump())
    except Exception as e:
        result = {'error': str(e)}
    try:
        return json.dumps(_to_jsonable(result), ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return json.dumps({'error': f'Serialization failed: {e}'}, ensure_ascii=False)
```

Only one functional change: `json.dumps(result, ...)` → `json.dumps(_to_jsonable(result), ...)`. The `except` block and error-dict paths are unchanged.

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/06_ask.ipynb
```

---

### Task 15: Add `_to_jsonable` unit test and `dispatch_tool` boundary contract test

**Files:**
- Modify: `nbs/06_ask.ipynb` — add two new test cells after cell `aaa22718` (the existing `dispatch_tool` test)

- [ ] **Step 1: Add `_to_jsonable` unit test cell**

Insert a new code cell after `aaa22718`:

```python
# Test: _to_jsonable handles BaseModel, list[BaseModel], nested dict, passthrough
from yttoc.ask import _to_jsonable
from yttoc.core import Segment

s = Segment(start=1.0, end=2.0, text='hi')

# Single BaseModel → dict
assert _to_jsonable(s) == {'start': 1.0, 'end': 2.0, 'text': 'hi'}

# list[BaseModel] → list[dict]
assert _to_jsonable([s, s]) == [
    {'start': 1.0, 'end': 2.0, 'text': 'hi'},
    {'start': 1.0, 'end': 2.0, 'text': 'hi'},
]

# Nested: dict containing a BaseModel
assert _to_jsonable({'a': s, 'b': 1}) == {'a': {'start': 1.0, 'end': 2.0, 'text': 'hi'}, 'b': 1}

# Nested: dict containing list[BaseModel]
assert _to_jsonable({'items': [s]}) == {'items': [{'start': 1.0, 'end': 2.0, 'text': 'hi'}]}

# Passthrough for scalars
assert _to_jsonable(42) == 42
assert _to_jsonable('abc') == 'abc'
assert _to_jsonable(None) is None

# Passthrough for plain dict / list (idempotent)
assert _to_jsonable({'x': 1, 'y': [2, 3]}) == {'x': 1, 'y': [2, 3]}

print('ok')
```

- [ ] **Step 2: Add `dispatch_tool` boundary contract test cell**

Insert another new code cell after the unit test cell:

```python
# Test: dispatch_tool serializes list[Segment] handler result as list of {start,end,text} dicts
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from yttoc.ask import dispatch_tool, build_registry

with TemporaryDirectory() as d:
    root = Path(d)
    v = root / 'VID_BND'; v.mkdir()
    (v / 'captions.en.srt').write_text(
        '1\n00:00:00,000 --> 00:00:03,000\nalpha\n\n'
        '2\n00:00:05,000 --> 00:00:08,000\nbeta\n')

    registry = build_registry(root)
    raw = dispatch_tool(registry, 'get_xscript_range',
                        '{"video_id":"VID_BND","start":0,"end":10}')
    parsed = json.loads(raw)
    assert isinstance(parsed, list), f'expected list, got {type(parsed)}'
    assert len(parsed) == 2
    for item in parsed:
        assert isinstance(item, dict)
        assert set(item.keys()) == {'start', 'end', 'text'}
        assert isinstance(item['start'], float)
        assert isinstance(item['end'], float)
        assert isinstance(item['text'], str)
print('ok')
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/06_ask.ipynb
```

---

### Task 16: Export, run full test suite, grep verify

**Files:** none (verification only).

- [ ] **Step 1: Export all notebooks**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-export
```

Expected: no errors.

- [ ] **Step 2: Run full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test
```

Expected: `Success.` — all notebooks green. If any fail, identify the notebook from the error, re-open the relevant task, fix, repeat.

- [ ] **Step 3: Grep — verify no remaining xscript-segment dict access**

```bash
cd /home/doyu/yttoc && grep -nE "s\[('|\")(start|end|text)(\1)\]" yttoc/core.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py
```

Expected output (TOC-section consumers are out of scope; xscript-segment consumers must NOT appear):

```
yttoc/toc.py:<line>:    sections = sorted(raw, key=lambda s: s['start'])
yttoc/toc.py:<line>:        if s['start'] not in seen:
yttoc/toc.py:<line>:            seen.add(s['start'])
yttoc/toc.py:<line>:            'start': s['start'],
```

These are the `_normalize_sections` hits — all on TOC-section dicts (not xscript segments) and thus out of Phase 2 Segment scope. Anything else indicates a missed consumer.

Additionally check `ask.py` for dict access on segments (not on TOC sections):

```bash
grep -nE "result\[0\]\[" yttoc/ask.py
```

Expected: no output (Test 14 in 02 was the only place doing this on xscript segments, and it was migrated in Task 9).

- [ ] **Step 4: Run `nbdev-prepare`**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-prepare
```

Expected: `Success.`

---

### Task 17: Stage, review, commit, push, open PR #2

**Files:** staging + git ops.

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/02_xscript.ipynb nbs/03_toc.ipynb nbs/04_summarize.ipynb nbs/06_ask.ipynb yttoc/core.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py yttoc/ask.py yttoc/_modidx.py
```

- [ ] **Step 2: Show diff for user review**

```bash
git status && git diff --cached --stat && git diff --cached | head -400
```

Expected: 5 notebooks modified, 6 generated `.py` files modified. Net insertions + deletions under 200 lines.

- [ ] **Step 3: Pause for user review**

Ask: "PR #2 staged diff ready. Approve to commit, or indicate changes?" Do NOT proceed until approved.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(pipeline): propagate Segment through xscript consumers

PR #2 of Phase 2 pilot — flips parse_xscript's return type from
list[dict] to list[Segment] and updates all 5 consumer sites
(slice_segments, _build_toc_prompt, _build_summary_prompt, yttoc_raw,
yttoc_txt CLI) to attribute access.

Adds _to_jsonable helper inside dispatch_tool so LLM-tool handlers
can return Pydantic models without breaking the JSON contract.

Test migration:
- 8 dict-literal fixtures in nbs/03 and nbs/04 rewritten as Segment(...)
- ~21 subscript assertions in nbs/02 Tests 1-7 and Test 14 rewritten
  as attribute access
- _to_jsonable unit test and dispatch_tool boundary contract test
  added in nbs/06

Internal dict shapes (NormalizedSection, Meta, AssembledSummaries)
remain dict-based; they are covered by separate follow-up specs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2-segment-propagate
gh pr create --title "refactor(pipeline): propagate Segment through xscript consumers (Phase 2 pilot PR #2)" --body "$(cat <<'EOF'
## Summary

Phase 2 pilot PR #2 — follows PR #1 which introduced `Segment` in `core`. This PR flips `parse_xscript` to return `list[Segment]` and updates all 5 xscript-segment consumer sites (`slice_segments`, `_build_toc_prompt`, `_build_summary_prompt`, `yttoc_raw` CLI, `yttoc_txt` CLI) to attribute access. Adds a `_to_jsonable` helper inside `dispatch_tool` so LLM-tool handlers returning Pydantic models are transparently serialized for the tool JSON contract.

## Test migration

- 8 dict-literal fixtures (nbs/03 Test 6: 2, nbs/04 Test 1: 4, nbs/04 Test 3: 2) → `Segment(...)` constructors
- ~21 subscript assertions in nbs/02 Tests 1-7 and Test 14 → attribute access
- New: `_to_jsonable` unit test (nbs/06)
- New: `dispatch_tool` boundary contract test — round-trips `get_xscript_range` and asserts the JSON is `list[{start, end, text}]`

## Scope boundary

Internal dict shapes `NormalizedSection` (toc.json), `Meta` (meta.json), and `AssembledSummaries` (summaries.json) are explicitly out of scope and remain dict-based. They are covered by separate follow-up specs per the design doc.

## Test plan

- [x] Full `nbdev-test` passes
- [x] `_to_jsonable` idempotent on plain dict / list / scalar
- [x] `dispatch_tool` JSON output preserves `{start, end, text}` shape for LLM contract

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI, user merge, resync main, delete branch**

```bash
gh pr checks <PR_NUMBER>
# after merge:
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2-segment-propagate 2>/dev/null || true && git log --oneline -5
```

---

### Task 18: Mark spec and plan as completed

**Files:**
- Move: `docs/superpowers/plans/2026-04-19-pydantic-phase2-segment.md` → `docs/superpowers/plans/done/2026-04-19-pydantic-phase2-segment.md`

- [ ] **Step 1: After PR #2 merges, move the plan to done/**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main
git mv docs/superpowers/plans/2026-04-19-pydantic-phase2-segment.md docs/superpowers/plans/done/
git commit -m "chore(plans): archive Phase 2 Segment plan"
git push origin main  # direct push OK for docs-only housekeeping — confirm with user first
```

If the user prefers PR flow even for plan housekeeping, replace the direct push with a feature branch + PR.

---

## Summary Checklist (end-state)

- [ ] PR #1 merged: `Segment` BaseModel lives in `yttoc/core`, `parse_xscript` uses it internally, public `list[dict]` return preserved, validation test passes
- [ ] PR #2 merged: `parse_xscript` returns `list[Segment]`, all 5 consumer sites use attribute access, `dispatch_tool` has `_to_jsonable` helper + boundary contract test, full `nbdev-test` green
- [ ] Plan archived under `docs/superpowers/plans/done/`
- [ ] Local `main` resynced with `origin/main`
