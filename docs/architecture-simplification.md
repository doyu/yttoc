# Architecture Simplification: Evaluation and Decision

Reviewed: 2026-04-21

This document merges:

- the original architecture simplification ideas
- the conservative review of those ideas
- the follow-up discussion that clarified the final direction

The goal is to record:

- what ideas were considered
- what the current code is actually doing
- why some ideas were rejected for now
- what the current recommended next steps are
- what might become reasonable later if the codebase grows

This is the canonical document.
Later reviews that recommend a conservative “thin helper” approach should be read as support for this final direction, not as a critique of an older draft.

## Current Architecture

`yttoc` is small, linear, and artifact-driven.

The current flow is:

1. `fetch` writes `meta.json` and `captions.*.srt`
2. `xscript` parses captions into normalized `Segment` objects
3. `toc` generates and writes `toc.json`
4. `summarize` generates and writes `summaries.json`
5. `map` and `ask` consume `summaries.json`

This is important because the main boundaries are explicit files, not hidden framework layers.

- `yttoc.fetch.fetch_video` creates the cached inputs
- `yttoc.toc.generate_toc` produces `toc.json`
- `yttoc.summarize.generate_summaries` produces `summaries.json`
- `yttoc.map.load_summaries` reads `summaries.json` directly
- `yttoc.ask.build_registry` exposes existing cached artifacts as LLM tools

That directness is currently a strength, not a weakness.

## What We Evaluated

The main ideas considered were:

1. unify LLM calls
2. separate cache/path concerns from stage logic
3. introduce a cache decorator
4. introduce a pipeline or DAG abstraction
5. rewrite model inheritance as composition
6. unify `ask.py` with the other LLM call sites

The final recommendation is intentionally conservative:

- adopt a thin `cache.py` helper
- adopt a thin `llm.py` helper
- do not add heavier abstractions yet

## Actual Code: Where The Friction Is

### 1. LLM call duplication is real, but small

There is obvious duplication between:

- `_call_llm` in [toc.py](/home/doyu/yttoc/yttoc/toc.py)
- `_call_summary_llm` in [summarize.py](/home/doyu/yttoc/yttoc/summarize.py)

Both functions do the same SDK ritual:

- create `openai.OpenAI()`
- call `chat.completions.create(...)`
- build `response_format` from a Pydantic model
- send one user prompt
- parse the JSON string with `model_validate_json(...)`

The real differences are small:

- the prompt text
- the schema name
- the response model
- whether the caller returns a model, `sections`, or `model_dump()`

So there is real repetition, but only across two functions.

### 2. Path and cache boilerplate is scattered

Several modules repeat the same storage logic:

- resolve `root`
- build `root / video_id`
- locate `meta.json`, `toc.json`, `summaries.json`
- find captions
- check required files
- read JSON and validate through Pydantic

This shows up in:

- `generate_toc` in [toc.py](/home/doyu/yttoc/yttoc/toc.py)
- `generate_summaries` in [summarize.py](/home/doyu/yttoc/yttoc/summarize.py)
- `_load_segments` and `_get_xscript_range_strict` in [xscript.py](/home/doyu/yttoc/yttoc/xscript.py)
- `_get_summaries_strict` in [summarize.py](/home/doyu/yttoc/yttoc/summarize.py)
- `load_summaries` in [map.py](/home/doyu/yttoc/yttoc/map.py)

The code is correct, but stage logic and storage logic are mixed together.

### 3. Some “duplication” is actually useful explicitness

Not all repeated code should be hidden.

For example, `generate_toc` does this on refresh:

- remove `toc.json`
- also remove `summaries.json`

That is not generic cache behavior.
That is a domain rule: summaries depend on TOC.

Likewise, `generate_summaries` explicitly calls `generate_toc` first.
That direct call is currently easier to understand than a framework-level dependency declaration.

## Idea 1: Introduce `instructor`

### Why it looked attractive

The original proposal correctly noticed that `toc.py` and `summarize.py` have nearly identical OpenAI structured-output code.

Using `instructor` would reduce boilerplate and give a clean-looking call site.

### Why it was rejected for now

The scope is too small.

Right now, the duplication is only:

- one helper in `toc.py`
- one helper in `summarize.py`

For that size, `instructor` would add:

- a new dependency
- a new abstraction layer around the OpenAI SDK
- a new calling style for future readers to learn

That is not a good trade yet.

### Final judgment

Reject for now.

The underlying idea was good, but the chosen mechanism was too heavy for the current repo size.

## Idea 2: Add a Thin Internal LLM Helper

### Why this was chosen

This keeps the good part of the original idea, while avoiding the dependency cost.

The helper should be very small and should only remove SDK ceremony.
It should not try to become a general LLM framework.

### Recommended shape

Put it in `yttoc/llm.py`.

Example:

```python
def generate_structured(
    prompt: str,
    response_model: type[BaseModel],
    *,
    schema_name: str,
    model: str = "gpt-5.4",
):
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=model,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": response_model.model_json_schema(),
            },
        },
        messages=[{"role": "user", "content": prompt}],
    )
    return response_model.model_validate_json(response.choices[0].message.content)
```

### What stays local

`toc.py` should still own:

- `_build_toc_prompt`
- `_normalize_sections`

`summarize.py` should still own:

- `_build_summary_prompt`
- `_assemble_summaries`

The helper should only hide:

- client creation
- schema wiring
- JSON parse/validation

### Why `ask.py` is excluded

`ask.py` is a different pattern.

It uses:

- `responses.parse`
- tool schema generation
- tool dispatch
- iterative tool-use loop
- structured final answer

That is not the same shape as “one prompt in, one structured object out”.

So the decision is:

- unify `toc.py` and `summarize.py`
- leave `ask.py` alone

## Idea 3: Add a Cache Decorator

### Why it looked attractive

The original proposal correctly noticed that `generate_toc` and `generate_summaries` mix:

- file access
- refresh behavior
- cache hit logic
- actual business logic

A decorator would make the functions shorter and more “pure”.

### Why it was rejected for now

It hides rules that are currently useful to read directly.

In this repo, cache behavior is not only:

- read if present
- compute if missing
- write result

It also includes meaning:

- refreshing TOC invalidates summaries
- generating summaries may force TOC generation first
- transcript reads still depend on actual caption files

Those are workflow rules, not just storage rules.

If they move into a generic decorator, the code becomes shorter but less obvious.

### Final judgment

Reject for now.

The idea identifies a real pain point, but the abstraction would hide too much of the stage semantics.

## Idea 4: Add a Thin Path / Cache Helper

### Why this was chosen

This keeps the explicit workflow while removing low-level storage noise.

The recommended helper is not a cache manager class and not a decorator.
It is a small module that centralizes path construction and file loading.

### Recommended placement

Put it in `yttoc/cache.py`, not `core.py`.

Reason:

- `core.py` is currently a clean data-model layer
- adding I/O helpers there would mix model definitions with storage concerns
- `cache.py` better matches the repo vocabulary: cached videos, cached artifacts, cache root

### Recommended shape

Good candidates:

```python
def resolve_root(root=None) -> Path: ...
def video_dir(video_id: str, root=None) -> Path: ...
def meta_path(video_id: str, root=None) -> Path: ...
def toc_path(video_id: str, root=None) -> Path: ...
def summaries_path(video_id: str, root=None) -> Path: ...
def first_srt_path(video_id: str, root=None) -> Path: ...

def load_meta(video_id: str, root=None) -> Meta: ...
def read_model(path: Path, model_cls: type[T]) -> T: ...
```

`load_meta` is safe here because `Meta` lives in `core.py`, which is already an upstream data-model module.

By contrast, `load_toc_file` and `load_summaries_file` are intentionally excluded.
Those would require `cache.py` to know about `TocFile` from `toc.py` and `AssembledSummaries` from `summarize.py`, which would risk dependency reversal and circular imports.

The intended usage is:

- `cache.py` owns path construction and generic file reading
- `toc.py` still owns `TocFile`
- `summarize.py` still owns `AssembledSummaries`
- callers pass their own model class into `read_model(...)`

### What stays out of the helper

The helper should not own refresh policy or invalidation policy.

That means these rules stay in the stage modules:

- `toc.py` still decides that refreshing TOC invalidates summaries
- `summarize.py` still decides to ensure TOC exists first

### Why this works better than a decorator

It gives most of the readability win without changing the architectural model.

After extraction, the stage functions should read more like orchestration:

`generate_toc`

1. locate required inputs
2. apply refresh policy
3. return cached result if present
4. load meta and transcript
5. build prompt
6. call LLM
7. normalize and save

`generate_summaries`

1. locate required inputs
2. apply refresh policy
3. return cached result if present
4. ensure TOC exists
5. load meta and transcript
6. build prompt
7. call LLM
8. assemble and save

That is the intended simplification.

## Idea 5: Rewrite Inheritance As Composition

### Current shape

The current model chain is:

- `NormalizedSection` in `core.py`
- `AssembledSection` in `summarize.py`
- `FlattenedSection` in `map.py`

Each stage adds fields to the same conceptual section.

### Why it looked questionable

Three levels of inheritance can feel “deep”, and composition can sometimes make data origin clearer.

### Why it was rejected for now

In this repo, the inheritance is still aligned with the data flow.

Examples:

- `AssembledSection(**sec.model_dump(), ...)` in `summarize.py`
- `FlattenedSection(**sec.model_dump(), ...)` in `map.py`

These are additive transformations on a section-shaped record.

If we switch to composition too early, many call sites likely become noisier:

- `row.title` becomes `row.section.title`
- `row.start` becomes `row.section.start`
- renderers and grouping code become more nested

There is no strong evidence yet that the current inheritance is causing real problems.

### Final judgment

Reject for now.

Revisit only if:

- behavior starts attaching to these models
- the inheritance chain gets deeper
- field collisions or ambiguity become common

## Idea 6: Introduce Pipeline / DAG Abstraction

### Why it looked attractive

At a high level, the repo is a pipeline:

- captions -> TOC -> summaries -> derived views

So it is natural to think about making that dependency graph explicit.

### Why it was rejected for now

The current code already expresses the dependencies plainly enough.

Examples:

- `generate_summaries` directly calls `generate_toc`
- `map.py` reads `summaries.json`
- `ask.py` exposes cached data through tools instead of re-deriving it

There is no branching workflow, no scheduler, no alternative backends, and no serious orchestration complexity yet.

A pipeline framework would add terms and structure without solving a pressing problem.

### Final judgment

Reject for now.

## Idea 7: Keep `ask.py` Tool Registry As Is

This part of the current code is already well-shaped.

The `ToolEntry` pattern in [ask.py](/home/doyu/yttoc/yttoc/ask.py) keeps:

- tool schema generation
- runtime argument validation
- tool handler wiring

in one place, with Pydantic as the single source of truth.

This is a good abstraction already.
No change is recommended here.

## Final Decision

Adopt only these two changes for now:

1. add `yttoc/cache.py`
2. add `yttoc/llm.py`

Do not adopt yet:

- `instructor`
- cache decorators
- pipeline/DAG abstraction
- inheritance-to-composition rewrite
- `ask.py` unification

## Why This Final Choice Wins

It preserves the current strengths of the repo:

- directness
- file-backed boundaries
- easy debugging
- obvious stage dependencies

while removing the two most mechanical kinds of repetition:

- path/cache boilerplate
- OpenAI structured-output boilerplate

In short:

- keep the architecture explicit
- only extract ceremony

## Future Possibilities

These ideas may become reasonable later if the repo changes shape.

### Revisit `instructor` if:

- there are many more structured LLM call sites
- retries and validation repair become important
- a thin local helper starts growing too much logic

### Revisit a richer cache abstraction if:

- cache invalidation rules multiply
- more artifact types are added
- multiple commands need the same read/write policy

### Revisit composition if:

- the section models gain behavior
- nesting becomes conceptually clearer than flattening
- inheritance stops reflecting the real data flow

### Revisit pipeline/DAG abstraction if:

- workflow branches appear
- stages become optional or pluggable
- scheduling, retries, or parallel execution become real needs

## Implementation Order

If this is implemented, the recommended order is:

1. add `cache.py`
2. refactor `toc.py`, `summarize.py`, `xscript.py`, and `map.py` to use its path helpers and generic reader
3. add `llm.py`
4. refactor `toc.py` and `summarize.py` to use it
5. stop there

That gives the repo a cleaner shape without changing what makes it understandable today.
