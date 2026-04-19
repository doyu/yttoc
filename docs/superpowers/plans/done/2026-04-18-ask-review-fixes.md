# ask module review fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 issues identified in the `nbs/06_ask.ipynb` code review — a broken first-response path, verbose default mismatch, missing pydantic dependency, and broad exception handling.

**Architecture:** All source changes go in `nbs/06_ask.ipynb` (nbdev source of truth). After each task, run `nbdev_export` to regenerate `yttoc/ask.py`. `pyproject.toml` is edited directly.

**Tech Stack:** Python, nbdev, Pydantic v2, OpenAI Responses API

---

### Task 1: Fix `ask()` initial response — use `responses.parse` for all turns

The current code uses `client.responses.create()` for the first API call (line 148 of `yttoc/ask.py`). If the model responds without tool calls on the first turn, `output_parsed` doesn't exist on the response object, so the function always falls through to `AskResponse(answer='No answer generated.')`.

**Fix:** Use `client.responses.parse(..., text_format=AskResponse)` for the initial call too, so `output_parsed` is available on every response.

**Files:**
- Modify: `nbs/06_ask.ipynb` — cell `ae69b791` (the `ask()` function)

- [ ] **Step 1: Edit the `ask()` function in `nbs/06_ask.ipynb`**

Replace the initial `responses.create` call with `responses.parse`:

```python
#| export
import openai

def ask(question: str, # Natural-language query
        video_ids: list[str], # Cached video IDs
        model: str = 'gpt-4o', # LLM model
        max_iterations: int = 20, # Safety cap on tool-use loop
        root: Path = None, # Cache root directory
        verbose: bool = False # Print tool calls to stderr
       ) -> AskResponse:
    "Run a tool-use loop to answer a question about a video course."
    from yttoc.fetch import _DEFAULT_ROOT
    root = root or _DEFAULT_ROOT
    client = openai.OpenAI()
    registry = build_registry(root)
    tools = openai_tools(registry)

    user_input = f"Video IDs: {json.dumps(video_ids)}\n---\nQuestion: {question}"

    response = client.responses.parse(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=user_input,
        tools=tools,
        text_format=AskResponse,
    )

    for _ in range(max_iterations):
        tool_calls = [item for item in response.output
                      if item.type == 'function_call']
        if not tool_calls:
            break

        tool_outputs = []
        for tc in tool_calls:
            if verbose:
                args = json.loads(tc.arguments)
                print(f'{tc.name}({", ".join(f"{k}={v!r}" for k,v in args.items())})',
                      file=sys.stderr)
            result = dispatch_tool(registry, tc.name, tc.arguments)
            tool_outputs.append({
                'type': 'function_call_output',
                'call_id': tc.call_id,
                'output': result,
            })

        response = client.responses.parse(
            model=model,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=tools,
            text_format=AskResponse,
        )

    if hasattr(response, 'output_parsed') and response.output_parsed is not None:
        return response.output_parsed

    return AskResponse(answer='No answer generated.', citations=[])
```

Note: this also changes `verbose` default from `True` to `False` (Task 2).

- [ ] **Step 2: Run `nbdev_export` and verify**

```bash
cd /home/doyu/yttoc && python -m nbdev.export
```

Expected: `yttoc/ask.py` regenerated with `responses.parse` on the initial call and `verbose=False`.

- [ ] **Step 3: Run tests**

```bash
cd /home/doyu/yttoc && nbdev_test --path nbs/06_ask.ipynb
```

Expected: All deterministic tests pass (format_citations, dispatch_tool tests).

- [ ] **Step 4: Commit**

```bash
git add nbs/06_ask.ipynb yttoc/ask.py
git commit -m "fix(ask): use responses.parse for initial call; set verbose=False"
```

---

### Task 2: Add `pydantic>=2` to `pyproject.toml` dependencies

`pydantic` is used directly (`BaseModel`, `Field`, `model_json_schema`, `model_validate_json`) but not listed in `dependencies`. It works today because `openai` SDK pulls it in transitively, but this is fragile.

**Files:**
- Modify: `pyproject.toml` — line 15

- [ ] **Step 1: Edit `pyproject.toml`**

Change:
```toml
dependencies = ["yt-dlp", "fastcore", "openai"]
```

To:
```toml
dependencies = ["yt-dlp", "fastcore", "openai", "pydantic>=2"]
```

- [ ] **Step 2: Verify install**

```bash
cd /home/doyu/yttoc && pip install -e . --quiet
python -c "import pydantic; print(pydantic.VERSION)"
```

Expected: Pydantic 2.x version printed.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pydantic>=2 to explicit dependencies"
```

---

### Task 3: Improve `dispatch_tool()` exception handling

Current code has two issues:
1. `except Exception` catches everything indiscriminately — Pydantic validation errors and runtime handler errors look the same.
2. `json.dumps(result)` on line 75 is outside the try block and can raise on non-serializable results.

**Files:**
- Modify: `nbs/06_ask.ipynb` — cell `b57a20ff` (the cell containing `dispatch_tool`)

- [ ] **Step 1: Edit `dispatch_tool` in the notebook**

Replace the current `dispatch_tool` function:

```python
def dispatch_tool(registry: dict[str, dict[str, Any]], name: str, raw_args: str) -> str:
    "Validate args via Pydantic, call handler, return JSON result."
    tool = registry.get(name)
    if tool is None:
        return json.dumps({'error': f'Unknown tool: {name}'}, ensure_ascii=False)
    try:
        args = tool['args_model'].model_validate_json(raw_args)
        result = tool['handler'](**args.model_dump())
    except Exception as e:
        result = {'error': str(e)}
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return json.dumps({'error': f'Serialization failed: {e}'}, ensure_ascii=False)
```

The key change: wrap `json.dumps` in its own try/except for serialization failures.

Note: We keep the single `except Exception` for validation+handler errors intentionally — splitting `ValidationError` from handler errors adds complexity without benefit since both produce `{"error": "..."}` for the LLM regardless. The important fix is protecting `json.dumps`.

- [ ] **Step 2: Run existing tests to verify dispatch_tool still works**

```bash
cd /home/doyu/yttoc && nbdev_test --path nbs/06_ask.ipynb
```

Expected: All tests pass, including the Pydantic validation error test case.

- [ ] **Step 3: Run `nbdev_export`**

```bash
cd /home/doyu/yttoc && python -m nbdev.export
```

- [ ] **Step 4: Commit**

```bash
git add nbs/06_ask.ipynb yttoc/ask.py
git commit -m "fix(ask): protect json.dumps in dispatch_tool against serialization errors"
```
