# Pydantic Schema Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-written JSON Schema dicts in toc and summarize modules with Pydantic `model_json_schema()` as single schema source, matching the pattern established in ask.py.

**Architecture:** This plan targets LLM output schemas only — the "external I/O contract" where hand-written JSON Schema and Python dict are currently double-managed. The API transport (`chat.completions.create`) is unchanged — only the schema source and response parsing change. Internal dict shapes (Section, Segment) are left for a future Phase 2. File format (toc.json, summaries.json) is unchanged — Pydantic generates the schema and validates LLM responses, then `.model_dump()` produces the same dicts as today.

**Tech Stack:** Python, Pydantic v2, OpenAI Chat Completions API (unchanged), nbdev

**Scope boundary:** This plan does NOT migrate from `chat.completions.create` to `responses.parse`. That is a separate concern (API transport change) which should be planned and tested independently.

---

## File Map

| File | Changes |
|------|---------|
| `nbs/03_toc.ipynb` | Add `RawTocSection`, `TocLLMResult` BaseModels. Replace `_TOC_SCHEMA` dict with `TocLLMResult.model_json_schema()`. Parse response via `TocLLMResult.model_validate_json()`. |
| `nbs/04_summarize.ipynb` | Add `Evidence`, `SectionSummaryPayload`, `SummaryLLMResult` BaseModels. Replace `_SUMMARY_SCHEMA` dict with `SummaryLLMResult.model_json_schema()`. Parse response via `SummaryLLMResult.model_validate_json()`. |
| `yttoc/toc.py` | Auto-generated from notebook via `nbdev-export` |
| `yttoc/summarize.py` | Auto-generated from notebook via `nbdev-export` |

**Not changed:** `nbs/00_core.ipynb`, `nbs/06_ask.ipynb`, `pyproject.toml` (pydantic already in deps), JSON file formats, OpenAI API transport method.

---

### Task 1: Add Pydantic models and replace `_TOC_SCHEMA` in toc

The current `_TOC_SCHEMA` is a 16-line hand-written JSON Schema dict. `_call_llm()` uses `chat.completions.create` with `response_format` and manually calls `json.loads()`. We replace the schema source with Pydantic and parse the response through the model, but keep `chat.completions.create`.

**Files:**
- Modify: `nbs/03_toc.ipynb` — cells `b1000004` (imports), `d95b70ae` (schema + _call_llm)

- [ ] **Step 1: Add Pydantic import to toc imports cell**

Replace cell `b1000004`:

```python
#| export
import json
from pathlib import Path
from pydantic import BaseModel, Field
```

- [ ] **Step 2: Define Pydantic models and replace `_TOC_SCHEMA` + update `_call_llm` parsing**

Replace cell `d95b70ae` with:

```python
#| export
def _build_toc_prompt(segments: list[dict], # [{start, end, text}, ...] from parse_xscript
                      meta: dict # meta.json content
                     ) -> str: # Prompt for LLM
    "Build a prompt that asks the LLM to identify topic transitions and return section titles with start times."
    lines = []
    for s in segments:
        mm = int(s['start'] // 60)
        ss = int(s['start'] % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {s['text']}")
    transcript = '\n'.join(lines)

    title = meta.get('title', '')
    channel = meta.get('channel', '')
    desc = meta.get('description', '')

    return f"""You are a structural editor for YouTube video transcripts.

Video info:
- Title: {title}
- Channel: {channel}
- Description: {desc}

Transcript:
{transcript}

Task:
Read the transcript and identify topic transitions. For each section, provide:
- title: concise English section title
- start: start time in integer seconds

Aim for 7-15 sections. Be faithful to transcript timestamps."""

class RawTocSection(BaseModel):
    "One section as returned by the TOC LLM — title + start time only."
    title: str = Field(description="Concise English section title")
    start: int = Field(ge=0, description="Start time in integer seconds")

class TocLLMResult(BaseModel):
    "Structured output from the TOC generation LLM call."
    sections: list[RawTocSection]

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

Key changes:
- `_TOC_SCHEMA` dict (16 lines) deleted — replaced by `TocLLMResult.model_json_schema()`
- `json.loads()` → `TocLLMResult.model_validate_json()` — adds Pydantic validation
- `chat.completions.create` unchanged — same API transport
- Return type unchanged: `list[dict]` — downstream `_normalize_sections` sees the same shape

- [ ] **Step 3: Run tests**

```bash
nbdev-test --path nbs/03_toc.ipynb
```

Expected: All 8 tests pass. Tests 1-6 test `_normalize_sections` and `_build_toc_prompt` (no LLM). Tests 7-8 use pre-cached toc.json (no LLM). No test calls `_call_llm` directly.

- [ ] **Step 4: Export and verify**

```bash
nbdev-export
```

Verify in `yttoc/toc.py`:
- `from pydantic import BaseModel, Field` present
- `RawTocSection` and `TocLLMResult` classes present
- `_TOC_SCHEMA` dict gone
- `_call_llm` still uses `chat.completions.create` with `TocLLMResult.model_json_schema()`

- [ ] **Step 5: Stage and request review**

```bash
git add nbs/03_toc.ipynb yttoc/toc.py
git diff --cached
```

Request user review of staged diff before committing.

---

### Task 2: Add Pydantic models and replace `_SUMMARY_SCHEMA` in summarize

The current `_SUMMARY_SCHEMA` is a 34-line hand-written JSON Schema dict with nested `evidence` objects. `_call_summary_llm()` uses `chat.completions.create` and `json.loads`. We replace the schema source with Pydantic and parse the response through the model, but keep `chat.completions.create`.

**Files:**
- Modify: `nbs/04_summarize.ipynb` — cells `c1000004` (imports), `404ff620` (schema + _call_summary_llm)

- [ ] **Step 1: Add Pydantic import to summarize imports cell**

Replace cell `c1000004`:

```python
#| export
import json
from pathlib import Path
from pydantic import BaseModel, Field
```

- [ ] **Step 2: Define Pydantic models and replace `_SUMMARY_SCHEMA` + update `_call_summary_llm` parsing**

Replace cell `404ff620` with:

```python
#| export
class Evidence(BaseModel):
    "A quoted phrase from the transcript with its timestamp."
    text: str = Field(description="Short quoted phrase from the transcript")
    at: int = Field(ge=0, description="Timestamp in seconds where the quote appears")

class SectionSummaryPayload(BaseModel):
    "Summary payload for one section or the full video."
    summary: str = Field(description="1-2 sentence English summary")
    keywords: list[str] = Field(description="Important terms (people, technical terms, proper nouns)")
    evidence: Evidence

class SummaryLLMResult(BaseModel):
    "Structured output from the summary generation LLM call."
    full: SectionSummaryPayload
    sections: dict[str, SectionSummaryPayload] = Field(
        description="Per-section summaries keyed by section path ('1', '2', ...)")

def _call_summary_llm(prompt: str) -> dict:
    "Call OpenAI gpt-5.4 with Pydantic-generated schema, return {full, sections} dict."
    import openai
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model='gpt-5.4',
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "generate_summaries",
                "schema": SummaryLLMResult.model_json_schema(),
            },
        },
        messages=[{"role": "user", "content": prompt}],
    )
    return SummaryLLMResult.model_validate_json(
        response.choices[0].message.content).model_dump()
```

Key changes:
- `_SUMMARY_SCHEMA` dict (34 lines) deleted — replaced by `SummaryLLMResult.model_json_schema()`
- `Evidence` is its own model — reusable, readable, replaces the nested dict-in-dict
- `json.loads()` → `SummaryLLMResult.model_validate_json()` — adds Pydantic validation
- `chat.completions.create` unchanged — same API transport
- Return type unchanged: `dict` — downstream `_assemble_summaries` sees the same shape

- [ ] **Step 3: Run tests**

```bash
nbdev-test --path nbs/04_summarize.ipynb
```

Expected: All 10 tests pass. No test calls `_call_summary_llm` directly — they all use pre-cached summaries.json or test `_assemble_summaries` / `_build_summary_prompt` with plain dicts.

- [ ] **Step 4: Export and verify**

```bash
nbdev-export
```

Verify in `yttoc/summarize.py`:
- `from pydantic import BaseModel, Field` present
- `Evidence`, `SectionSummaryPayload`, `SummaryLLMResult` classes present
- `_SUMMARY_SCHEMA` dict gone
- `_call_summary_llm` still uses `chat.completions.create` with `SummaryLLMResult.model_json_schema()`

- [ ] **Step 5: Stage and request review**

```bash
git add nbs/04_summarize.ipynb yttoc/summarize.py
git diff --cached
```

Request user review of staged diff before committing.

---

### Task 3: Cross-module integration test and finalize

Verify that the full pipeline still works end-to-end after both refactors.

**Files:**
- No file changes — verification only

- [ ] **Step 1: Run all affected notebook tests**

```bash
nbdev-test --path nbs/03_toc.ipynb && nbdev-test --path nbs/04_summarize.ipynb && nbdev-test --path nbs/06_ask.ipynb
```

Expected: All tests pass across all three modules.

- [ ] **Step 2: Run full test suite**

```bash
nbdev-test
```

Expected: All notebooks pass.

- [ ] **Step 3: Verify schema generation matches intent**

```bash
python -c "
from yttoc.toc import TocLLMResult
from yttoc.summarize import SummaryLLMResult
import json
print('=== TocLLMResult schema ===')
print(json.dumps(TocLLMResult.model_json_schema(), indent=2))
print()
print('=== SummaryLLMResult schema ===')
print(json.dumps(SummaryLLMResult.model_json_schema(), indent=2))
"
```

Verify:
- `TocLLMResult` schema has `sections` array with `title` (string) and `start` (integer, minimum 0)
- `SummaryLLMResult` schema has `full` and `sections` with `summary`, `keywords`, `evidence.text`, `evidence.at`

- [ ] **Step 4: Verify Pydantic models are exported**

```bash
python -c "
from yttoc.toc import RawTocSection, TocLLMResult
from yttoc.summarize import Evidence, SectionSummaryPayload, SummaryLLMResult
print('All models importable')
"
```

Expected: No ImportError.

- [ ] **Step 5: Run nbdev-prepare and stage**

```bash
nbdev-prepare
git add -u
git diff --cached
```

Request user review of staged diff before committing.
