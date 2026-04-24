# LLM Structured Output: `create()` + `raw_decode()` over `parse()`

Decided: 2026-04-25

## Background

`yttoc/llm.py::generate_structured` calls OpenAI for structured output and validates the response against a Pydantic model. While running `yttoc-sum EN7frwQIbKc`, the call failed with:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for TocLLMResult
  Invalid JSON: trailing characters at line 2 column 1
```

The model returned `{"sections":[...]}\n<extra content>`. `model_validate_json` requires the entire string to be a single JSON document, so it rejected the trailing bytes.

## Root cause

The original implementation used:

```python
response_format={
    'type': 'json_schema',
    'json_schema': {
        'name': schema_name,
        'schema': response_model.model_json_schema(),
    },
}
```

This is **non-strict** structured output. OpenAI treats the schema as a hint, not a hard grammar constraint. Models can append a second JSON object, prose, or stray whitespace after the primary value.

## Options considered

### Option A — `client.chat.completions.parse()` with Pydantic

```python
response = client.chat.completions.parse(
    model=model,
    response_format=response_model,   # Pydantic class directly
    messages=[...],
)
return response.choices[0].message.parsed
```

Why attractive:

- `parse()` always uses **strict mode**, where OpenAI enforces the schema at the grammar level. Trailing content becomes physically impossible.
- Removes hand-rolled `json_schema` dict, the `model_json_schema()` call, the `model_validate_json` call, and the `schema_name` parameter.
- Recommended pattern by OpenAI for structured output.

Why rejected:

The summary LLM result uses an open dict:

```python
class SummaryLLMResult(BaseModel):
    full: SectionSummaryPayload
    sections: dict[str, SectionSummaryPayload]
```

Pydantic emits this as `{"type": "object", "additionalProperties": {...}}` — no fixed `properties`. OpenAI's strict-mode transform rejects it:

```
400 Invalid schema for response_format 'SummaryLLMResult':
'required' is required to be supplied and to be an array including every
key in properties. Extra required key 'sections' supplied.
```

Adopting `parse()` would have required reshaping the LLM contract from `dict[str, SectionSummaryPayload]` keyed by section path to `list[PathedSummary]` carrying the path as a field, plus updating the prompt that documents the response shape, plus a list→dict adapter inside `_call_summary_llm` to keep `_assemble_summaries` unchanged. That is a separable redesign, not a fix for the trailing-characters bug.

### Option B — `create()` + `raw_decode()` *(adopted)*

Keep the existing non-strict `json_schema` request, but extract the first JSON value:

```python
content = response.choices[0].message.content
obj, _ = json.JSONDecoder().raw_decode(content.lstrip())
return response_model.model_validate(obj)
```

Why adopted:

- One-line behavior change. No schema reshape, no prompt rewrite, no API surface change.
- Robust to the observed failure mode (JSON object followed by trailing whitespace, prose, or a second JSON object).
- Symmetric for both `TocLLMResult` (list-based) and `SummaryLLMResult` (dict-based) — no per-caller branching.
- Test added in `nbs/08_llm.ipynb` covers the trailing-content case.

## When to revisit

If we end up with more callers, or if OpenAI relaxes strict-mode constraints around `additionalProperties`, the cleaner path is:

1. Refactor `SummaryLLMResult.sections` from `dict[str, ...]` to `list[PathedSummary]` (path as a field).
2. Update the summary prompt's response-shape description.
3. Adapter inside `_call_summary_llm` converts list → dict so `_assemble_summaries` is untouched.
4. Switch `generate_structured` to `client.chat.completions.parse()` and drop `schema_name`.

That brings us back to Option A with full strict-mode safety. It is intentionally deferred — the current bug does not justify it.
