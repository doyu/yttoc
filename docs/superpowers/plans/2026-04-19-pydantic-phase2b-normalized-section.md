# Pydantic Phase 2b — NormalizedSection / toc.json Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `NormalizedSection` Pydantic model and a `TocFile` envelope model, propagate them through the TOC pipeline (`_normalize_sections` → `generate_toc` → on-disk `toc.json` I/O → `xscript._load_segments` / `summarize._build_summary_prompt` / `summarize._assemble_summaries`), and migrate the corresponding notebook tests. Split into two PRs: PR-A adds models API-preservingly; PR-B flips return types and wraps file I/O with `TocFile.model_validate_json`.

**Architecture:** `NormalizedSection` lives in `nbs/00_core.ipynb` (shared type — avoids the `xscript → toc` circular import that would arise if it lived in `toc`). `TocFile` lives in `nbs/03_toc.ipynb` (file-I/O schema owned by the toc module). `_call_llm`'s inter-private-function chain becomes fully typed (`list[RawTocSection]` → `_normalize_sections` → `list[NormalizedSection]`). Downstream consumers are updated notebook-by-notebook in PR-B; `format_toc_line`, `_print_section_summary`, `_find_section`, and `map.py` are explicitly out of scope and deferred to Phase 2d when `AssembledSummaries` gets typed.

**Tech Stack:** Python, nbdev 3, Pydantic v2. All `nbdev-*` commands run from `/home/doyu/yttoc/` under `.venv`.

**Spec:** `docs/superpowers/specs/2026-04-19-pydantic-phase2b-normalized-section-design.md` (commit `ee35cc0`).

**Execution environment:** Use `/home/doyu/yttoc/.venv/bin/python`, `/home/doyu/yttoc/.venv/bin/nbdev-export`, `/home/doyu/yttoc/.venv/bin/nbdev-test` directly. Edit notebooks by loading their JSON in Python, mutating target cells' `source`, writing back, then running `scripts/normalize_notebooks.py`. Do not rely on Jupyter interactivity.

**AGENTS.md compliance checkpoints:**
- Stage for review (`git diff --cached`) before every commit.
- No direct push to `main`; each PR is a feature branch.
- One feature per PR. Rebase-merge on GitHub; delete branch after merge; `git reset --hard origin/main` locally to resync.

---

## File Structure

### PR-A — touches
- `nbs/00_core.ipynb` — add `NormalizedSection` BaseModel + validation test
- `nbs/03_toc.ipynb` — add `TocFile` BaseModel + validation test, retype `_call_llm` and `_normalize_sections`, migrate Tests 1-5 input fixtures
- Generated `yttoc/core.py`, `yttoc/toc.py`, `yttoc/_modidx.py` — regenerated

### PR-B — touches
- `nbs/03_toc.ipynb` — flip `_normalize_sections` + `generate_toc` return, wrap `toc.json` I/O via `TocFile`, migrate Tests 7-8 assertions, add corruption-rejection test
- `nbs/02_xscript.ipynb` — `_load_segments` reads `toc.json` via `TocFile`, `sec_info` uses attribute access
- `nbs/04_summarize.ipynb` — `_build_summary_prompt` + `_assemble_summaries` attribute access on toc-sections parameter, migrate Test 3 `sections` fixture
- Generated `yttoc/toc.py`, `yttoc/xscript.py`, `yttoc/summarize.py`, `yttoc/_modidx.py`

---

## PR-A — Introduce `NormalizedSection` and `TocFile` (API-preserving, ~40 lines)

### Task 1: Create PR-A feature branch

**Files:** none

- [ ] **Step 1: Verify clean main**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main && git status
```

Expected: `On branch main`, `nothing to commit, working tree clean`.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2b-models
```

Expected: `Switched to a new branch 'refactor/pydantic-phase2b-models'`.

---

### Task 2: Add `NormalizedSection` BaseModel to `nbs/00_core.ipynb` + validation test

**Files:**
- Modify: `nbs/00_core.ipynb` — cell `ec3460e1` (adds class); insert a new test cell immediately after cell `96d993a7` (the existing Segment validation test)

- [ ] **Step 1: Inspect current cell `ec3460e1`**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/00_core.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'ec3460e1':
        print(''.join(c['source']))
"
```

Expected: the cell starts with `#| export`, then `from pydantic import BaseModel, Field`, then `class Segment(BaseModel): ...`, then `def fmt_duration(...)`, `def format_header(...)`, `def slice_segments(...)`, `def format_toc_line(...)`. No `NormalizedSection`.

- [ ] **Step 2: Insert `NormalizedSection` immediately after the `Segment` class definition**

Target the position in the cell source between `class Segment(...)` (with its 3 fields) and `def fmt_duration(...)`. Add:

```python
class NormalizedSection(BaseModel):
    "One TOC section after normalization (path and end added to raw LLM output)."
    path: str = Field(description="Section path like '1', '2', ...")
    title: str = Field(description="Concise English section title")
    start: int = Field(ge=0, description="Start time in integer seconds")
    end: int = Field(ge=0, description="End time in integer seconds")
```

Leave `Segment`, `fmt_duration`, `format_header`, `slice_segments`, `format_toc_line` bit-identical.

- [ ] **Step 3: Insert a new code cell after cell `96d993a7` for the NormalizedSection validation test**

Create a new code cell via Python (load notebook JSON, find index of cell with `id == '96d993a7'`, insert new cell at that index + 1). New cell structure: `cell_type: code`, fresh 8-char hex `id`, empty `metadata`, empty `outputs`, `execution_count: None`, `source` split into lines with newline terminators. New cell source:

```python
# Test: NormalizedSection validates required fields and non-negative bounds
from yttoc.core import NormalizedSection
from pydantic import ValidationError

# Valid construction succeeds
s = NormalizedSection(path='1', title='Intro', start=0, end=300)
assert s.path == '1' and s.title == 'Intro' and s.start == 0 and s.end == 300

# Negative start rejected
try:
    NormalizedSection(path='1', title='x', start=-1, end=10)
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative start'

# Negative end rejected
try:
    NormalizedSection(path='1', title='x', start=0, end=-1)
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative end'

# Missing required field rejected
try:
    NormalizedSection(path='1', title='x', start=0)  # no end
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing end'

print('ok')
```

- [ ] **Step 4: Normalize + export + test**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/00_core.ipynb && .venv/bin/nbdev-export && .venv/bin/nbdev-test --path nbs/00_core.ipynb
```

Expected: `normalized: nbs/00_core.ipynb`, no export errors, `Success.`.

- [ ] **Step 5: Verify import works**

```bash
/home/doyu/yttoc/.venv/bin/python -c "from yttoc.core import NormalizedSection; print(NormalizedSection(path='1', title='x', start=0, end=10))"
```

Expected: `path='1' title='x' start=0 end=10`.

---

### Task 3: Add `TocFile` BaseModel + validation test to `nbs/03_toc.ipynb`

**Files:**
- Modify: `nbs/03_toc.ipynb` — cell `b1000004` (imports), cell `d95b70ae` (existing cell containing `_build_toc_prompt`, `RawTocSection`, `TocLLMResult`, `_call_llm`); insert a new test cell immediately after cell `b1000011` (Test 5 — `_normalize_sections` empty-input test)

- [ ] **Step 1: Inspect current state**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/03_toc.ipynb'))
for c in nb['cells']:
    if c.get('id') in ('b1000004','d95b70ae'):
        print(f'=== {c[\"id\"]} ===')
        print(''.join(c['source']))
        print()
"
```

Expected: `b1000004` contains `import json`, `from pathlib import Path`, `from pydantic import BaseModel, Field`, `from yttoc.core import Segment`. `d95b70ae` contains `_build_toc_prompt`, `RawTocSection`, `TocLLMResult`, `_call_llm`.

- [ ] **Step 2: Update `b1000004` — import `NormalizedSection`**

Edit cell `b1000004` source to append `from yttoc.core import NormalizedSection` OR extend the existing `from yttoc.core import Segment` line to `from yttoc.core import Segment, NormalizedSection`. The final cell content should be exactly:

```python
#| export
import json
from pathlib import Path
from pydantic import BaseModel, Field
from yttoc.core import Segment, NormalizedSection
```

- [ ] **Step 3: Add `TocFile` class inside cell `d95b70ae`**

Locate the `class TocLLMResult(BaseModel):` block in cell `d95b70ae`. Immediately after the `TocLLMResult` definition (just before the `def _call_llm(...)` function), insert:

```python
class TocFile(BaseModel):
    "On-disk shape of toc.json."
    sections: list[NormalizedSection]
```

Leave everything else in the cell untouched.

- [ ] **Step 4: Insert TocFile validation test cell after cell `b1000011`**

Via Python JSON mutation, insert a new code cell (fresh 8-char hex `id`) immediately after the cell with `id == 'b1000011'`. Source:

```python
# Test: TocFile validates envelope shape and element types
from yttoc.toc import TocFile
from pydantic import ValidationError

# Valid
toc = TocFile.model_validate_json(
    '{"sections": [{"path":"1","title":"Intro","start":0,"end":300}]}'
)
assert len(toc.sections) == 1
assert toc.sections[0].title == 'Intro'

# Missing 'sections' key rejected
try:
    TocFile.model_validate_json('{"section": []}')  # typo
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing sections key'

# Bad element shape (missing 'end') rejected
try:
    TocFile.model_validate_json(
        '{"sections": [{"path":"1","title":"x","start":0}]}'
    )
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for missing end field'

# Negative timestamp rejected via NormalizedSection constraint
try:
    TocFile.model_validate_json(
        '{"sections": [{"path":"1","title":"x","start":-1,"end":10}]}'
    )
except ValidationError:
    pass
else:
    assert False, 'expected ValidationError for negative start'

print('ok')
```

- [ ] **Step 5: Normalize + export + test**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb && .venv/bin/nbdev-export && .venv/bin/nbdev-test --path nbs/03_toc.ipynb
```

Expected: `Success.` (Tests 1-5 use `raw = [{...}]` dict literals and still pass since `_normalize_sections` still accepts `list[dict]` — those migrate in Task 5).

- [ ] **Step 6: Verify TocFile import**

```bash
/home/doyu/yttoc/.venv/bin/python -c "from yttoc.toc import TocFile; print(TocFile(sections=[]))"
```

Expected: `sections=[]`.

---

### Task 4: Switch `_call_llm` and `_normalize_sections` to use Pydantic internally

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `b1000005` (`_normalize_sections`) and `d95b70ae` (contains `_call_llm`)

`_normalize_sections`'s input changes from `list[dict]` to `list[RawTocSection]`. It still returns `list[dict]` (public API preserved for PR-A). `_call_llm` drops the trailing `.model_dump()` conversion.

- [ ] **Step 1: Edit cell `d95b70ae` — `_call_llm` drops `.model_dump()`**

Find the current `_call_llm` function's return statement (at the very end of the cell):

```python
def _call_llm(prompt: str # Full prompt
             ) -> list[dict]: # [{title, start}, ...]
    "Call OpenAI gpt-5.4 with Pydantic-generated schema, return raw section list."
    import openai
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model='gpt-5.4',
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "generate_toc",
                "schema": TocLLMResult.model_json_schema(),
            },
        },
        messages=[{"role": "user", "content": prompt}],
    )
    result = TocLLMResult.model_validate_json(response.choices[0].message.content)
    return [s.model_dump() for s in result.sections]
```

Apply exactly two edits:
1. Return annotation: `list[dict]` → `list[RawTocSection]`
2. Inline comment `[{title, start}, ...]` → `List of RawTocSection`
3. Final `return [s.model_dump() for s in result.sections]` → `return list(result.sections)`

- [ ] **Step 2: Edit cell `b1000005` — `_normalize_sections` accepts `list[RawTocSection]`, constructs `NormalizedSection` internally**

Replace the entire `_normalize_sections` function body with:

```python
def _normalize_sections(raw: 'list[RawTocSection]', # [RawTocSection, ...] from LLM
                        duration: int # Video duration in seconds
                       ) -> list[dict]: # [{path, title, start, end}, ...]
    "Add path/end, sort by start, dedup, validate. Raise on broken coverage."
    if not raw:
        raise ValueError("No sections returned from LLM")
    # Sort by start ascending
    sections = sorted(raw, key=lambda s: s.start)
    # Remove duplicate starts (keep first)
    seen = set()
    deduped = []
    for s in sections:
        if s.start not in seen:
            seen.add(s.start)
            deduped.append(s)
    sections = deduped
    # Fix first section start to 0 (create a new RawTocSection with start=0)
    sections[0] = RawTocSection(title=sections[0].title, start=0)
    # Build NormalizedSection list
    result = []
    for i, s in enumerate(sections):
        end = sections[i+1].start if i+1 < len(sections) else duration
        result.append(NormalizedSection(path=str(i+1), title=s.title, start=s.start, end=end))
    return [ns.model_dump() for ns in result]
```

Key changes:
- Annotation `list[dict]` → **string** `'list[RawTocSection]'` on the `raw` parameter (forward reference — `RawTocSection` is defined later in cell `d95b70ae`, so at def-time evaluation it is not yet in scope. A string annotation defers resolution.). Runtime references to `RawTocSection` inside the body (e.g., `RawTocSection(title=..., start=0)` below) are evaluated at call time, by which point `d95b70ae` has already executed.
- All `s['start']` / `s['title']` → `s.start` / `s.title`.
- `{**sections[0], 'start': 0}` dict-spread → new `RawTocSection(title=..., start=0)` construction.
- Dict-literal result → `NormalizedSection(...)` construction (note: `NormalizedSection` comes from `yttoc.core` which is imported eagerly in `b1000004`, so no forward-ref needed for it).
- Final `return result` is now `return [ns.model_dump() for ns in result]` to preserve the public `list[dict]` contract.

- [ ] **Step 3: Normalize + export**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb && .venv/bin/nbdev-export
```

Expected: no export errors.

- [ ] **Step 4: Run tests (they will fail until Task 5)**

```bash
cd /home/doyu/yttoc && .venv/bin/nbdev-test --path nbs/03_toc.ipynb 2>&1 | tail -20
```

Expected: Failures in Tests 1-5 because fixtures still pass dict literals to `_normalize_sections` which now expects `list[RawTocSection]`. This is expected interim state; Task 5 fixes the fixtures.

---

### Task 5: Migrate Tests 1-5 input fixtures to `RawTocSection(...)` constructors

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `b1000007`, `b1000008`, `b1000009`, `b1000010`, `b1000011`

- [ ] **Step 1: Update cell `b1000007` (Test 1)**

Replace its full body with:

```python
# Test 1: basic — adds path and computes end from next start; last end = duration
from yttoc.toc import RawTocSection
raw = [RawTocSection(title='Intro', start=0),
       RawTocSection(title='Main', start=300),
       RawTocSection(title='Outro', start=600)]
secs = _normalize_sections(raw, duration=900)
assert len(secs) == 3
assert secs[0] == {'path': '1', 'title': 'Intro', 'start': 0, 'end': 300}
assert secs[1] == {'path': '2', 'title': 'Main', 'start': 300, 'end': 600}
assert secs[2] == {'path': '3', 'title': 'Outro', 'start': 600, 'end': 900}
print('ok')
```

- [ ] **Step 2: Update cell `b1000008` (Test 2)**

```python
# Test 2: sorts by start ascending
from yttoc.toc import RawTocSection
raw = [RawTocSection(title='B', start=300), RawTocSection(title='A', start=0)]
secs = _normalize_sections(raw, duration=600)
assert secs[0]['title'] == 'A'
assert secs[1]['title'] == 'B'
print('ok')
```

- [ ] **Step 3: Update cell `b1000009` (Test 3)**

```python
# Test 3: removes duplicate starts (keeps first occurrence after sort)
from yttoc.toc import RawTocSection
raw = [RawTocSection(title='A', start=0),
       RawTocSection(title='A-dup', start=0),
       RawTocSection(title='B', start=300)]
secs = _normalize_sections(raw, duration=600)
assert len(secs) == 2
assert secs[0]['title'] == 'A'
assert secs[1]['title'] == 'B'
print('ok')
```

- [ ] **Step 4: Update cell `b1000010` (Test 4)**

```python
# Test 4: fixes first section start to 0 if not already
from yttoc.toc import RawTocSection
raw = [RawTocSection(title='Late start', start=30), RawTocSection(title='Next', start=300)]
secs = _normalize_sections(raw, duration=600)
assert secs[0]['start'] == 0
assert secs[0]['end'] == 300
print('ok')
```

- [ ] **Step 5: Update cell `b1000011` (Test 5)**

No fixture change needed — Test 5 passes an empty list and asserts the `ValueError`. The body already works: `_normalize_sections([], duration=600)` raises on the `if not raw:` check (empty list is falsy regardless of element type). Verify the cell source still reads:

```python
# Test 5: empty input raises ValueError
try:
    _normalize_sections([], duration=600)
    assert False, 'should have raised'
except ValueError:
    pass
print('ok')
```

Leave as-is.

- [ ] **Step 6: Normalize + run full test suite**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb && .venv/bin/nbdev-test
```

Expected: `Success.` — all notebooks pass. Tests 6, 7, 8 in `nbs/03` pass because the public return shape of `_normalize_sections` and `generate_toc` is still `list[dict]`.

---

### Task 6: Stage, commit, push, open PR-A

**Files:** staging + git ops.

- [ ] **Step 1: Stage**

```bash
cd /home/doyu/yttoc && git add nbs/00_core.ipynb nbs/03_toc.ipynb yttoc/core.py yttoc/toc.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff for user review**

```bash
git status && git diff --cached --stat && git diff --cached
```

Expected: 5 files changed. `yttoc/core.py` gains `NormalizedSection` class. `yttoc/toc.py` gains `TocFile` class, `_call_llm` returns `list(result.sections)`, `_normalize_sections` uses `.start`/`.title` attribute access internally and returns `[ns.model_dump() for ns in result]`.

- [ ] **Step 3: Pause for user review**

Ask the user: "PR-A staged diff ready. Approve to commit, or indicate changes?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(core,toc): introduce NormalizedSection and TocFile (PR-A)

Phase 2b pilot PR-A — adds NormalizedSection to yttoc.core (shared
pipeline type; placed in core to avoid the xscript→toc circular
import that putting it in toc would create) and TocFile envelope
model to yttoc.toc (file-I/O schema). _call_llm now returns
list[RawTocSection] and _normalize_sections constructs NormalizedSection
internally but still returns list[dict] via model_dump, keeping the
public generate_toc contract unchanged. Tests 1-5 in nbs/03_toc.ipynb
migrated to RawTocSection(...) input fixtures.

PR-B follow-up will flip the public return to list[NormalizedSection]
and wrap toc.json I/O with TocFile.model_validate_json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2b-models
gh pr create --title "refactor(core,toc): introduce NormalizedSection and TocFile (Phase 2b PR-A)" --body "$(cat <<'EOF'
## Summary

Phase 2b pilot PR-A — adds \`NormalizedSection\` to \`yttoc.core\` and \`TocFile\` envelope to \`yttoc.toc\`. \`_call_llm\` now returns \`list[RawTocSection]\` and \`_normalize_sections\` constructs \`NormalizedSection\` internally. \`generate_toc\` public return shape stays \`list[dict]\` via \`.model_dump()\` — zero consumer impact. PR-B follow-up flips the return type and adds on-read/on-write validation.

Ownership rationale: \`NormalizedSection\` lives in \`core\` because \`toc\` already imports \`parse_xscript\` from \`xscript\`; placing it in \`toc\` would create an \`xscript → toc → xscript\` cycle when \`xscript._load_segments\` reads toc.json. See spec \`docs/superpowers/specs/2026-04-19-pydantic-phase2b-normalized-section-design.md\`.

## Test plan

- [x] \`nbdev-test\` full suite passes (public contract unchanged)
- [x] New test: \`NormalizedSection(start=-1, ...)\` raises \`ValidationError\`; missing required field raises
- [x] New test: \`TocFile.model_validate_json\` rejects missing envelope key and bad element shapes
- [x] Tests 1-5 in nbs/03_toc.ipynb migrated from dict literals to \`RawTocSection(...)\` constructors

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI and user merge**

```bash
gh pr checks <PR_NUMBER>
```

Stop here. Do NOT proceed to PR-B until user merges PR-A and confirms local `main` is resynced.

- [ ] **Step 7: After merge, resync local main**

```bash
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2b-models 2>/dev/null || true && git log --oneline -3
```

---

## PR-B — Propagate `NormalizedSection` + wrap `toc.json` I/O (~130-150 lines)

**⚠ Atomic refactor note:** PR-B flips `_normalize_sections` / `generate_toc` return types and wraps all `toc.json` reads in `TocFile.model_validate_json`. Between Task 9 and Task 13, tests will fail mid-PR because consumers still use dict subscript. Only run the full `nbdev-test` at Task 14; individual targeted tests may be used for quick sanity checks during intermediate tasks.

### Task 7: Pre-implementation cache validation check

**Files:** none (verification only).

- [ ] **Step 1: Run the sanity check against any existing cached `toc.json` files**

```bash
/home/doyu/yttoc/.venv/bin/python <<'PYEOF'
from pathlib import Path
from yttoc.toc import TocFile
cache_root = Path.home() / '.cache' / 'yttoc'
if not cache_root.exists():
    print('No cache root; skipping.')
else:
    found = list(cache_root.glob('*/toc.json'))
    if not found:
        print('No toc.json files in cache; skipping.')
    for f in found:
        try:
            TocFile.model_validate_json(f.read_text(encoding='utf-8'))
            print(f'OK: {f}')
        except Exception as e:
            print(f'FAIL: {f} → {e}')
PYEOF
```

Expected: every `toc.json` prints `OK:` (or the skip message if no cache exists). Any `FAIL:` means the spec's assumption that the on-disk shape matches `TocFile` exactly is wrong — STOP and escalate. The fix is either updating `NormalizedSection`/`TocFile` to match reality or writing a one-shot cache migration; do not proceed to PR-B until this is resolved.

---

### Task 8: Create PR-B feature branch

**Files:** none

- [ ] **Step 1: Verify clean main and PR-A merged**

```bash
cd /home/doyu/yttoc && git checkout main && git status
```

Expected: clean; `git log -1` shows the PR-A merge commit from origin.

- [ ] **Step 2: Create branch**

```bash
git checkout -b refactor/pydantic-phase2b-propagate
```

---

### Task 9: Flip `_normalize_sections` return + `generate_toc` return + wrap `toc.json` I/O

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `b1000005` (`_normalize_sections`) and `795bea0d` (`generate_toc`, `yttoc_toc`)

- [ ] **Step 1: Edit cell `b1000005` — `_normalize_sections` returns `list[NormalizedSection]`**

In the `_normalize_sections` function:

1. Return annotation `list[dict]` → `list[NormalizedSection]`.
2. Inline comment `[{path, title, start, end}, ...]` → `List of NormalizedSection`.
3. Final `return [ns.model_dump() for ns in result]` → `return result`.

Leave everything else (sort / dedup / first-fix / construction loop) bit-identical.

- [ ] **Step 2: Inspect cell `795bea0d` (`generate_toc` and `yttoc_toc`)**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/03_toc.ipynb'))
for c in nb['cells']:
    if c.get('id') == '795bea0d':
        print(''.join(c['source']))
"
```

Expected: contains `generate_toc(...)` with cached read `json.loads(toc_path.read_text(...))['sections']`, write `toc_path.write_text(json.dumps({'sections': sections}, ...))`, and `yttoc_toc` CLI that loops `for s in sections: print(format_toc_line(s, url))`.

- [ ] **Step 3: Edit cell `795bea0d` — flip `generate_toc` return + wrap I/O via `TocFile`**

Apply these edits inside `generate_toc`:

1. Return annotation `list[dict]` → `list[NormalizedSection]`. Inline comment `Normalized sections` → `List of NormalizedSection`.
2. Cached-read line `return json.loads(toc_path.read_text(encoding='utf-8'))['sections']` → `return TocFile.model_validate_json(toc_path.read_text(encoding='utf-8')).sections`.
3. File-write block:

   ```python
   toc_path.write_text(
       json.dumps({'sections': sections}, indent=2, ensure_ascii=False),
       encoding='utf-8')
   ```
   becomes:
   ```python
   toc_path.write_text(
       TocFile(sections=sections).model_dump_json(indent=2),
       encoding='utf-8')
   ```

`yttoc_toc` CLI body: the existing loop `for s in sections: print(format_toc_line(s, url))` stays as-is. `format_toc_line` is out of scope per the spec; it still accepts `s` and internally does `s['start']` etc. Pydantic v2 `BaseModel` instances are NOT dict-subscriptable by default — but `format_toc_line` is called from two places (here with `NormalizedSection`, and from `summarize._print_section_summary` with a summaries-json-section dict), and Phase 2b leaves `format_toc_line` untouched. To make `yttoc_toc` still work, convert each section to a dict just before handing to `format_toc_line`:

Replace:
```python
for s in sections:
    print(format_toc_line(s, url))
```
with:
```python
for s in sections:
    print(format_toc_line(s.model_dump(), url))
```

This keeps `format_toc_line` dict-typed (Phase 2d cleanup) while giving it valid input.

- [ ] **Step 4: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

---

### Task 10: Migrate Tests 7-8 assertions in `nbs/03_toc.ipynb`

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `971d3b0c` (Test 7) and `f0fb87b4` (Test 8)

After Task 9, `generate_toc` returns `list[NormalizedSection]`. The file-write fixtures in Tests 7-8 (pre-populating `toc.json` on disk) stay as dict literals — they represent the on-disk JSON format and are read through `TocFile.model_validate_json`. Only the assertions on the Python return value change.

- [ ] **Step 1: Edit cell `971d3b0c` (Test 7)**

Find the final assertions:
```python
secs = generate_toc('VID1', root)
assert len(secs) == 2
assert secs[0]['title'] == 'Intro'
assert secs[1]['title'] == 'Main'
```
Replace the two `['title']` subscripts with `.title` attribute access:
```python
secs = generate_toc('VID1', root)
assert len(secs) == 2
assert secs[0].title == 'Intro'
assert secs[1].title == 'Main'
```

The dict literals inside `(v / 'toc.json').write_text(json.dumps({'sections': [{'path': ...}, ...]}))` are unchanged — they're serialized JSON input for the read path.

- [ ] **Step 2: Edit cell `f0fb87b4` (Test 8)**

Test 8 captures stdout from `yttoc_toc` and asserts strings appear. No Python-value subscripts on TOC sections — this test only asserts on stdout content. Leave the assertions as-is. Leave the dict-literal fixtures in the `toc.json` write as-is (they're on-disk JSON input).

Verify via grep:
```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/03_toc.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'f0fb87b4':
        src = ''.join(c['source'])
        print(src)
"
```
Expected: no `s['path']` / `s['title']` / `s['start']` / `s['end']` patterns appearing on a Python value (only inside the dict-literal JSON-serialization path).

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb
```

---

### Task 11: Update `xscript._load_segments` — toc.json read via `TocFile`, `sec_info` attribute access

**Files:**
- Modify: `nbs/02_xscript.ipynb` — cell `bcd5731c` (contains `_load_segments`, `yttoc_raw`, `yttoc_txt`)

- [ ] **Step 1: Inspect the cell**

```bash
/home/doyu/yttoc/.venv/bin/python -c "
import json
nb = json.load(open('/home/doyu/yttoc/nbs/02_xscript.ipynb'))
for c in nb['cells']:
    if c.get('id') == 'bcd5731c':
        print(''.join(c['source']))
"
```

Expected: contains imports `from yttoc.core import fmt_duration, format_header, slice_segments, Segment`, a `_load_segments` helper reading `toc.json` via `json.loads` and selecting via `next((s for s in toc['sections'] if s['path'] == section), None)`, and `yttoc_raw` / `yttoc_txt` CLI functions using `sec_info['start']`, `sec_info['end']`, `sec_info['title']`.

- [ ] **Step 2: Extend the `yttoc.core` import to include `NormalizedSection`**

Change the import line from:
```python
from yttoc.core import fmt_duration, format_header, slice_segments, Segment
```
to:
```python
from yttoc.core import fmt_duration, format_header, slice_segments, Segment, NormalizedSection
```

- [ ] **Step 3: Add a `TocFile` import from yttoc.toc**

Immediately after the `from .fetch import ...` line, add:
```python
from yttoc.toc import TocFile
```

- [ ] **Step 4: Update `_load_segments` — toc.json read via `TocFile`**

Find the existing block:
```python
if section:
    toc_path = d / 'toc.json'
    if not toc_path.exists():
        raise SystemExit(f"No toc.json for {video_id}. Run yttoc-toc first.")
    toc = json.loads(toc_path.read_text(encoding='utf-8'))
    sec_info = next((s for s in toc['sections'] if s['path'] == section), None)
    if sec_info is None:
        raise SystemExit(f"Section {section} not found")
    segments = slice_segments(segments, sec_info['start'], sec_info['end'])
```

Replace with:
```python
if section:
    toc_path = d / 'toc.json'
    if not toc_path.exists():
        raise SystemExit(f"No toc.json for {video_id}. Run yttoc-toc first.")
    toc = TocFile.model_validate_json(toc_path.read_text(encoding='utf-8'))
    sec_info = next((s for s in toc.sections if s.path == section), None)
    if sec_info is None:
        raise SystemExit(f"Section {section} not found")
    segments = slice_segments(segments, sec_info.start, sec_info.end)
```

Also update `_load_segments`'s return annotation. Find:
```python
def _load_segments(video_id: str, section: str, root: str | None
                  ) -> tuple[dict, list[Segment], dict | None, Path]:
```
Change to:
```python
def _load_segments(video_id: str, section: str, root: str | None
                  ) -> tuple[dict, list[Segment], NormalizedSection | None, Path]:
```

- [ ] **Step 5: Update `yttoc_raw` and `yttoc_txt` — `sec_info` attribute access**

Both functions have an identical block:
```python
if sec_info is not None:
    s_start = fmt_duration(sec_info['start'])
    s_end = fmt_duration(sec_info['end'])
    print(f"## {section}. {sec_info['title']} ({s_start} - {s_end})")
```

Replace both occurrences with:
```python
if sec_info is not None:
    s_start = fmt_duration(sec_info.start)
    s_end = fmt_duration(sec_info.end)
    print(f"## {section}. {sec_info.title} ({s_start} - {s_end})")
```

- [ ] **Step 6: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/02_xscript.ipynb
```

---

### Task 12: Update `summarize._build_summary_prompt` and `summarize._assemble_summaries` — attribute access on toc sections

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cells `c1000005` (`_build_summary_prompt`) and `d286018a` (`_assemble_summaries`, `_migrate_old_summaries`, `generate_summaries`, `_print_section_summary`, `yttoc_sum`)

- [ ] **Step 1: Edit cell `c1000005` — update `_build_summary_prompt` signature and loop**

In cell `c1000005`:

1. Update the imports to add `NormalizedSection`. Change `from yttoc.core import slice_segments, Segment` to `from yttoc.core import slice_segments, Segment, NormalizedSection`.

2. Update `_build_summary_prompt` signature — change the `sections` parameter type from `list[dict]` to `list[NormalizedSection]` and update its inline comment:

   Before:
   ```python
   def _build_summary_prompt(segments: list[Segment], # Full xscript segments
                             sections: list[dict], # [{path, title, start, end}, ...] from toc.json
                             meta: dict # meta.json content
                            ) -> str: # Prompt for LLM
   ```
   After:
   ```python
   def _build_summary_prompt(segments: list[Segment], # Full xscript segments
                             sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                             meta: dict # meta.json content
                            ) -> str: # Prompt for LLM
   ```

3. Inside the loop body, rewrite the 4 subscript accesses on `sec` to attribute access:

   Before:
   ```python
   for sec in sections:
       sliced = slice_segments(segments, sec['start'], sec['end'])
       lines = []
       for s in sliced:
           mm = int(s.start // 60)
           ss = int(s.start % 60)
           lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
       parts.append(f"### Section {sec['path']}: {sec['title']}\n" + '\n'.join(lines))
   ```
   After:
   ```python
   for sec in sections:
       sliced = slice_segments(segments, sec.start, sec.end)
       lines = []
       for s in sliced:
           mm = int(s.start // 60)
           ss = int(s.start % 60)
           lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
       parts.append(f"### Section {sec.path}: {sec.title}\n" + '\n'.join(lines))
   ```

- [ ] **Step 2: Edit cell `d286018a` — update `_assemble_summaries`**

In cell `d286018a`:

1. Extend the imports. Change `from yttoc.core import fmt_duration, format_header, format_toc_line` to `from yttoc.core import fmt_duration, format_header, format_toc_line, NormalizedSection`.

2. Update `_assemble_summaries` signature and body. Before:
   ```python
   def _assemble_summaries(meta: dict, # meta.json content
                           toc_sections: list[dict], # [{path, title, start, end}, ...] from toc.json
                           llm_result: dict # {full, sections: {path: {...}}}
                          ) -> dict: # Self-contained summaries.json payload
       "Merge meta + toc + LLM output into the canonical summaries.json shape. Raise if LLM omitted any section."
       missing = [sec['path'] for sec in toc_sections if sec['path'] not in llm_result['sections']]
       if missing:
           raise ValueError(f"LLM omitted summaries for sections: {missing}")
       return {
           'video': {...},
           'sections': [
               {'path': sec['path'], 'title': sec['title'],
                'start': sec['start'], 'end': sec['end'],
                **llm_result['sections'][sec['path']]}
               for sec in toc_sections
           ],
           'full': llm_result['full'],
       }
   ```

   After:
   ```python
   def _assemble_summaries(meta: dict, # meta.json content
                           toc_sections: list[NormalizedSection], # List of NormalizedSection from toc.json
                           llm_result: dict # {full, sections: {path: {...}}}
                          ) -> dict: # Self-contained summaries.json payload
       "Merge meta + toc + LLM output into the canonical summaries.json shape. Raise if LLM omitted any section."
       missing = [sec.path for sec in toc_sections if sec.path not in llm_result['sections']]
       if missing:
           raise ValueError(f"LLM omitted summaries for sections: {missing}")
       return {
           'video': {
               'id': meta.get('id'),
               'title': meta.get('title'),
               'channel': meta.get('channel'),
               'url': meta.get('webpage_url'),
               'duration': meta.get('duration'),
               'upload_date': meta.get('upload_date'),
           },
           'sections': [
               {**sec.model_dump(), **llm_result['sections'][sec.path]}
               for sec in toc_sections
           ],
           'full': llm_result['full'],
       }
   ```

   Note: `{**sec.model_dump(), **llm_result['sections'][sec.path]}` produces the same shape as the old dict-spread of `path`, `title`, `start`, `end` — because `NormalizedSection.model_dump()` yields exactly those four keys.

3. Leave `_migrate_old_summaries`, `generate_summaries`, `_print_section_summary`, `yttoc_sum` UNCHANGED. `_print_section_summary` takes `s: dict` (a summaries.json section, Phase 2d territory) and uses `format_toc_line(s, url)` — those stay as dict access per the spec's out-of-scope section.

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 13: Migrate Test 3 `sections` fixture in `nbs/04_summarize.ipynb`

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cell `c1000009`

Test 3 already has `segments` migrated to `Segment(...)` constructors (from Phase 2 pilot PR-B). This step migrates the `sections` fixture to `NormalizedSection(...)` constructors.

- [ ] **Step 1: Edit cell `c1000009`**

Find the existing `sections = [...]` block:
```python
sections = [
    {'path': '1', 'title': 'Intro', 'start': 0, 'end': 5},
    {'path': '2', 'title': 'Main', 'start': 5, 'end': 10},
]
```
Replace with:
```python
from yttoc.core import NormalizedSection
sections = [
    NormalizedSection(path='1', title='Intro', start=0, end=5),
    NormalizedSection(path='2', title='Main', start=5, end=10),
]
```

Leave the `segments = [Segment(...), ...]` fixture, the `meta = {...}` dict, the `prompt = _build_summary_prompt(...)` call, and the `assert ... in prompt` lines unchanged.

- [ ] **Step 2: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb
```

---

### Task 14: Add corruption-rejection test + cache-hit smoke test in `nbs/03_toc.ipynb`

**Files:**
- Modify: `nbs/03_toc.ipynb` — insert two new code cells after cell `f0fb87b4` (the last existing `generate_toc` / `yttoc_toc` test)

- [ ] **Step 1: Insert corruption-rejection test cell**

New code cell (fresh 8-char hex `id`), source:

```python
# Test 9: TocFile rejects a corrupted toc.json (negative start)
from tempfile import TemporaryDirectory
from pydantic import ValidationError

with TemporaryDirectory() as d:
    root = Path(d)
    v = root / 'VID_BAD'; v.mkdir()
    (v / 'captions.en.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nhi\n')
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID_BAD', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID_BAD',
        'last_used_at': '2000-01-01T00:00:00'}))
    # Corrupted toc.json — negative start violates NormalizedSection(start ≥ 0)
    (v / 'toc.json').write_text(json.dumps({'sections': [
        {'path': '1', 'title': 'Intro', 'start': -1, 'end': 300},
    ]}))

    try:
        generate_toc('VID_BAD', root)
    except ValidationError:
        pass
    else:
        assert False, 'expected ValidationError for negative start in toc.json'
print('ok')
```

- [ ] **Step 2: Insert cache-hit smoke test cell**

New code cell (fresh 8-char hex `id`), source:

```python
# Test 10: generate_toc cache-hit returns list[NormalizedSection] with typed fields
from tempfile import TemporaryDirectory
from yttoc.core import NormalizedSection

with TemporaryDirectory() as d:
    root = Path(d)
    v = root / 'VID_OK'; v.mkdir()
    (v / 'captions.en.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nhi\n')
    (v / 'meta.json').write_text(json.dumps({
        'id': 'VID_OK', 'title': 'T', 'channel': 'C', 'duration': 600,
        'upload_date': '20260101', 'webpage_url': 'https://youtube.com/watch?v=VID_OK',
        'last_used_at': '2000-01-01T00:00:00'}))
    (v / 'toc.json').write_text(json.dumps({'sections': [
        {'path': '1', 'title': 'Intro', 'start': 0, 'end': 300},
        {'path': '2', 'title': 'Main', 'start': 300, 'end': 600},
    ]}))

    secs = generate_toc('VID_OK', root)
    assert len(secs) == 2
    assert all(isinstance(s, NormalizedSection) for s in secs)
    assert secs[0].path == '1' and secs[0].title == 'Intro' and secs[0].start == 0 and secs[0].end == 300
    assert secs[1].path == '2' and secs[1].title == 'Main' and secs[1].start == 300 and secs[1].end == 600
print('ok')
```

- [ ] **Step 3: Normalize**

```bash
cd /home/doyu/yttoc && .venv/bin/python scripts/normalize_notebooks.py nbs/03_toc.ipynb
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

- [ ] **Step 3: Grep verify — no NormalizedSection subscript access in the in-scope files**

```bash
cd /home/doyu/yttoc && grep -nE "(sec|s)\[('|\")(path|title|start|end)(\1)\]" yttoc/toc.py yttoc/xscript.py yttoc/summarize.py
```

Expected output (each line must be matched against the spec's out-of-scope list):
- `yttoc/summarize.py` — hits inside `_print_section_summary` (reads `s['summary']`, `s['keywords']`, `s['evidence']['text']`) — OK, out of scope (summaries.json section)
- `yttoc/summarize.py` — hits inside `_assemble_summaries` that access `llm_result['sections'][sec.path]` — NOT a subscript on a NormalizedSection; OK
- Any hit on a `NormalizedSection`-typed variable (e.g., inside `generate_toc`, `_normalize_sections`, `_load_segments`, `_build_summary_prompt`, or the `toc_sections` path of `_assemble_summaries`) is a bug — fix before proceeding.

Additionally check `yttoc/core.py`:

```bash
grep -nE "section\[('|\")(path|title|start|end)(\1)\]" yttoc/core.py
```

Expected: hits inside `format_toc_line` only (4 hits). That's out of scope (Phase 2d); all other occurrences would be unexpected.

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
cd /home/doyu/yttoc && git add nbs/02_xscript.ipynb nbs/03_toc.ipynb nbs/04_summarize.ipynb yttoc/core.py yttoc/xscript.py yttoc/toc.py yttoc/summarize.py yttoc/_modidx.py
```

- [ ] **Step 2: Show staged diff**

```bash
git status && git diff --cached --stat && git diff --cached | head -500
```

Expected: 3 notebooks + 5 generated `.py` files modified. Net change under 200 lines.

- [ ] **Step 3: Pause for user review**

Ask: "PR-B staged diff ready. Approve to commit, or indicate changes?" Wait for explicit approval.

- [ ] **Step 4: Commit**

```bash
cd /home/doyu/yttoc && git commit -m "$(cat <<'EOF'
refactor(toc,xscript,summarize): propagate NormalizedSection (PR-B)

PR-B of Phase 2b — flips _normalize_sections and generate_toc to
return list[NormalizedSection], wraps toc.json I/O with
TocFile.model_dump_json / TocFile.model_validate_json, and updates
the in-scope consumers (_load_segments in xscript, _build_summary_prompt
and _assemble_summaries in summarize) to attribute access.

Out of scope: format_toc_line in core, _print_section_summary in
summarize, _find_section in ask, map.py — all receive wider
(summaries.json) section shapes and are covered by Phase 2d.

Tests:
- Tests 7-8 in nbs/03 assertions migrated from subscript to
  attribute access
- Test 3 sections fixture in nbs/04 rewritten as NormalizedSection(...)
- New: TocFile corruption-rejection test (negative start rejected)
- New: generate_toc cache-hit smoke test asserting list[NormalizedSection]
  with typed fields

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin refactor/pydantic-phase2b-propagate
gh pr create --title "refactor(toc,xscript,summarize): propagate NormalizedSection (Phase 2b PR-B)" --body "$(cat <<'EOF'
## Summary

Phase 2b pilot PR-B — follows PR-A (introducing \`NormalizedSection\` and \`TocFile\`). Flips \`_normalize_sections\` and \`generate_toc\` to return \`list[NormalizedSection]\`, wraps \`toc.json\` I/O with \`TocFile\` envelope validation, and propagates attribute access through:

- \`xscript._load_segments\` — reads \`toc.json\` via \`TocFile.model_validate_json\`
- \`summarize._build_summary_prompt\` — \`sections\` parameter typed as \`list[NormalizedSection]\`
- \`summarize._assemble_summaries\` — \`toc_sections\` parameter typed; spread merge uses \`sec.model_dump()\`

## Scope boundary

Out of scope (Phase 2d): \`format_toc_line\` in core, \`_print_section_summary\` in summarize, \`_find_section\` in ask, \`map.py\`. These accept wider (summaries.json) section shapes where \`AssembledSection\` will subclass \`NormalizedSection\`; Phase 2d unifies the type.

## Test plan

- [x] Full \`nbdev-test\` passes
- [x] Corruption-rejection test: \`generate_toc\` raises \`ValidationError\` on \`toc.json\` with negative start
- [x] Cache-hit smoke test: \`generate_toc\` returns \`list[NormalizedSection]\` with typed fields
- [x] Existing cached \`toc.json\` files validate against \`TocFile\` (pre-flight check run before branch)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI, user merge, resync main**

```bash
gh pr checks <PR_NUMBER>
# after merge:
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main && git branch -d refactor/pydantic-phase2b-propagate 2>/dev/null || true && git log --oneline -5
```

---

### Task 17: Archive plan

**Files:**
- Move: `docs/superpowers/plans/2026-04-19-pydantic-phase2b-normalized-section.md` → `docs/superpowers/plans/done/`

- [ ] **Step 1: After PR-B merges, create housekeeping PR**

```bash
cd /home/doyu/yttoc && git checkout main && git pull --ff-only origin main
git checkout -b chore/archive-phase2b-plan
git mv docs/superpowers/plans/2026-04-19-pydantic-phase2b-normalized-section.md docs/superpowers/plans/done/
git commit -m "chore(plans): archive Phase 2b NormalizedSection pilot plan"
git push -u origin chore/archive-phase2b-plan
gh pr create --title "chore(plans): archive Phase 2b NormalizedSection pilot plan" --body "Both implementation PRs are merged. Moving the plan under \`done/\` alongside previously completed plans. Docs-only change."
```

- [ ] **Step 2: After CI green, merge the housekeeping PR + resync**

```bash
gh pr merge <PR_NUMBER> --rebase --delete-branch
cd /home/doyu/yttoc && git checkout main && git fetch origin && git reset --hard origin/main
```

---

## Summary Checklist (end-state)

- [ ] PR-A merged: `NormalizedSection` in `yttoc.core`, `TocFile` in `yttoc.toc`, `_call_llm` returns `list[RawTocSection]`, `_normalize_sections` uses models internally, public API unchanged, all validation tests pass
- [ ] PR-B merged: `_normalize_sections` and `generate_toc` return `list[NormalizedSection]`, `toc.json` I/O wrapped in `TocFile`, `xscript._load_segments` / `summarize._build_summary_prompt` / `summarize._assemble_summaries` (toc-sections path) switched to attribute access, Tests 7-8 assertions and Test 3 fixture migrated, corruption + smoke tests added
- [ ] Plan archived under `docs/superpowers/plans/done/`
- [ ] Local `main` resynced with `origin/main`
