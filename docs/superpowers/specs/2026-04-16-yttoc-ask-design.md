# yttoc-ask: Cross-Video Question Answering — Design Document

**Status:** Draft
**Date:** 2026-04-16
**Author:** Hiroshi Doyu (with Claude)

## 0. Guiding Principle: Tool Use Is the Modern LLM App Primitive

The biggest advantage of a modern LLM is **tool use** — the LLM chooses which functions to call, with which arguments, in what order, on the fly to accomplish a larger task. In other words: *automatic API mashup performed by the LLM*. The application's job is not to pre-digest data into a prompt; it is to expose a small set of well-typed primitives and let the LLM orchestrate them.

This principle shapes every design decision in this document. Concretely:

- **Do not write Python that decides what data the LLM will need.** If we find ourselves building a "load everything that might be relevant" function, we are encoding retrieval logic in Python that the LLM should be doing itself.
- **Expose thin tools over existing primitives; do not design a new data contract.** Each tool should be a direct wrapper over an existing cache file or function. If a tool's result shape differs from the underlying data, we are inventing schema on the LLM's behalf.
- **Let the loop, not the prompt, handle scale.** When the corpus grows, the LLM simply makes more tool calls. No "fallback retrieval path" to implement.
- **Emergent queries beat designed queries.** Users will ask things the designer never anticipated. A tool-use loop handles these for free.

Anti-pattern to watch for: any paragraph where *we* are deciding what the LLM should see, rather than giving the LLM the means to decide for itself.

## 1. Problem Specification

**User need:** Given a curated list of YouTube video IDs (e.g., Jeremy Howard's 11-video "Solveit 2" course), the user wants to find the exact moment across all videos that addresses a question or concept they have in mind — and jump directly to that timestamp on YouTube.

**Why existing tools fall short:**

- `yttoc-find` (shell function in `README.md`) uses fzf over section titles + keywords. It works when the user remembers a phrase, but fails for conceptual queries where the right words aren't in the title.
- `yttoc-map` gives a hierarchical TOC view — good for browsing, not for question-driven lookup.
- Neither tool generates an *answer*; both return pointers and leave synthesis to the human.

**Success criteria:** Given a natural-language question and a list of video IDs, return (a) a synthesized answer and (b) one or more clickable `youtu.be/<id>?t=<seconds>` citations grounded in the actual transcript content.

## 2. Project Context

**yttoc** is an nbdev-based Python package that processes YouTube videos into structured knowledge assets. Per cached video (`~/.cache/yttoc/<video_id>/`):

| File | Created by | Content |
|------|-----------|---------|
| `meta.json` | `yttoc-fetch` | Title, channel, duration, upload date, URL |
| `captions.<lang>.srt` | `yttoc-fetch` | Raw captions in the video's original spoken language. `<lang>` resolved via `_glob_srt(d, 'captions.*.srt')` |
| `toc.json` | `yttoc-toc` (LLM) | Hierarchical section boundaries + titles |
| `summaries.json` | `yttoc-sum` (LLM) | `{video, sections, full}` — self-contained (embeds video metadata, section boundaries, summaries, keywords, evidence) |

**`yttoc-ask` is a read-only application.** It reads from an already-prepared cache. If data is missing for a video, the tool returns an error and the LLM informs the user that the video is unavailable. Cache preparation is a separate concern handled by the existing pipeline (`yttoc-fetch` → `yttoc-toc` → `yttoc-sum`); remediation guidance belongs in documentation, not in the app's runtime behavior.

This separation keeps `yttoc-ask` minimal: no side-effect tools, no pipeline orchestration, no auto-repair logic. The LLM's job is reasoning over data, not building caches.

Existing CLIs (Python, registered in `pyproject.toml`): `yttoc-fetch`, `yttoc-list`, `yttoc-raw`, `yttoc-txt`, `yttoc-toc`, `yttoc-sum`, `yttoc-map`.

`yttoc-find` is a **shell function** documented in `README.md`, not a Python CLI.

## 3. Key Constraints and Observations

Measured for the 11-video Solveit 2 course:

| Data | Size | ~Tokens |
|------|------|---------|
| All `summaries.json` | 131 KB | ~33k |
| All full transcripts (plain prose) | 1.1 MB | ~281k |

Under tool use, the LLM fetches only what it needs, so corpus size is manageable rather than a hard constraint. However, broad queries fan out `get_summaries` across all videos (O(N)), so the design is best suited for curated courses of moderate size.

## 4. Proposed Design

### 4.1 New CLI: `yttoc-ask`

```
yttoc-ask "AoCでNumPyを使うメリットは？" $(cat solveit2.id)
```

Inputs:

- `<question>`: natural-language query (first positional arg)
- `<video_id>...`: one or more cached video IDs (remaining positional args)
- `--model <name>`: LLM model (default: provider's recommended model for tool use)
- `--max-iterations <n>`: safety cap on the tool-use loop, not a retrieval policy (default: 20; sufficient because OpenAI supports parallel tool calls — raise if needed for larger corpora)

**Unix composition:** `yttoc-ask` does one thing — answer a question over a given set of videos. Reading IDs from a file is the shell's job (`$(cat file)`, `xargs`, etc.).

**Progress and diagnostics:** go to stderr. Examples: `get_summaries(7T83srD0Mu4)`, `get_xscript_range(ZUu302-sNSY, 4832, 5340)`.

Output (stdout, plain text):

```
<synthesized answer, 2-5 sentences>

Citations:
  [1] <Video Title> §<path> "<section title>" @ MM:SS
      https://youtu.be/<id>?t=<seconds>
  [2] ...
```

### 4.2 Tools Exposed to the LLM

Two read-only tools. Each is a direct wrapper over existing cached data. No side-effect tools.

| Tool | Input | Output | Backed by |
|------|-------|--------|-----------|
| `get_summaries` | `video_id` | `summaries.json` verbatim: `{video: {...}, sections: [...], full: {...}}`. Returns `{"error": "..."}` if missing | `summaries.json` read, no transformation |
| `get_xscript_range` | `video_id`, `start`, `end` | `[{start: <float>, end: <float>, text: "..."}, ...]` — raw parsed segments within the time range. Returns `{"error": "..."}` if cache missing | `captions.<lang>.srt` parsed via `parse_xscript()` + `slice_segments(start, end)` |

**Why `get_summaries` returns the file verbatim:** §0 says "do not design a new data contract." The tool returns exactly what `summaries.json` contains — including the `full` field (video-level summary + keywords) that earlier drafts dropped. No field filtering, no reshaping.

**Why `get_xscript_range(video_id, start, end)` instead of `get_xscript(video_id, section_path)`:** the previous `section_path` design had Python resolving path → `{start, end}` internally. But the LLM already has section boundaries from `get_summaries` — it can pass `start` and `end` directly. This removes a Python-side abstraction (section path lookup) and makes the tool a thinner wrapper over the raw primitive (`parse_xscript` + `slice_segments`). The return shape `{start, end, text}` matches `parse_xscript`'s output exactly — no field renaming.

**Purity note:** the absolute rawest primitive would be `get_xscript(video_id)` returning the entire parsed transcript. Range slicing is a convenience layer for token efficiency — without it, the LLM would receive the full ~100KB transcript per video. This is a deliberate purity-vs-efficiency tradeoff; the slicing logic itself (`slice_segments`) is an existing function, not new code.

**Why no side-effect tools:** `yttoc-ask` is a read-only reasoning shell. Auto-repair (fetch + toc + sum) would require either a compound `prepare_video` tool (Python encoding the pipeline — §0 violation) or exposing each pipeline step as a tool (adds complexity for an uncommon path). Instead, missing data is the user's responsibility via existing CLIs. This keeps `yttoc-ask` minimal.

**Error return format:** both tools return `{"error": "<message>"}` on failure, consistently.

**SRT language resolution:** `get_xscript_range` finds the SRT file via `_glob_srt(d, 'captions.*.srt')` — same mechanism used by all existing CLIs.

### 4.3 Interaction Loop

```
SYSTEM: You are answering questions about a video course.
        Use the provided tools to look up information. Do not fabricate content.
        Answer in the user's language. If data is unavailable, say so.

USER:   Video IDs: [video_id_1, video_id_2, ...]
        ---
        Question: <user query>
```

The system prompt does not prescribe tool-use strategy (no "call X then Y" instructions). The LLM discovers what to do from the tool schemas and error returns.

Response format: OpenAI Structured Outputs (`response_format`):

```json
{
  "answer": "synthesized answer text",
  "citations": [
    {"video_id": "7T83srD0Mu4", "seconds": 2535}
  ]
}
```

The citation schema is minimal: `{video_id, seconds}` only. Python looks up the section path, section title, and video title from cached `summaries.json` — the LLM is not asked to do bookkeeping it doesn't need for reasoning.

Processing steps:

1. Seed the conversation with the system prompt and a user message containing the video ID list and question.
2. Run the tool-use loop (OpenAI Responses API):
   - LLM emits tool calls → Python dispatcher executes → returns tool results
   - Repeat until the LLM returns the structured `{answer, citations}` response
3. Cap at `--max-iterations` (default 20).
4. Format output: answer text, then resolved citations with YouTube deep links.

**Typical exchanges (illustrative, not prescriptive):**

*Broad query:* "how does NumPy speed up the AoC solution?" → LLM fans out `get_summaries` across 11 videos (parallel), scans section summaries/keywords, calls `get_xscript_range` on relevant sections using `start`/`end` from summaries, returns answer with precise `seconds` from transcript segments.

*Narrow query:* "what does Lesson 3 §5 cover?" → LLM calls `get_summaries` for one video, reads section 5's start/end, calls `get_xscript_range`, answers.

*Missing data:* LLM calls `get_summaries(abc123)` → `{"error": "summaries.json not found for abc123"}` → LLM informs the user that this video is unavailable.

## 5. Citation Resolution

The LLM returns `[{video_id, seconds}]`. How it chose `seconds` — from transcript segments, `evidence.at`, or section `start` — is the LLM's decision, not specified here.

Python post-processing (display formatting only):

- For each `{video_id, seconds}`: find the containing section in `summaries.json` (where `start <= seconds < end`)
- Look up video title, section path, and section title
- Emit: `<Video Title> §<path> "<section title>" @ MM:SS` + `https://youtu.be/<id>?t=<seconds>`

The LLM returns the minimum needed for a deep link; Python handles all display enrichment.

## 6. Rejected Alternatives

| Alternative | Why rejected |
|-------------|--------------|
| Full-context prompting | Encodes retrieval logic in Python. Does not scale. Wastes tokens on narrow queries. |
| Embedding-based retrieval (FAISS, OpenAI embeddings) | ~170 sections is too small for a vector store. Tool use reduces hand-written retrieval logic. |
| `prepare_video` compound tool | Python encoding the fetch→toc→sum pipeline — §0 violation. Mixes read and write concerns. |
| Exposing `yttoc_fetch`/`yttoc_sum` as tools | Adds side-effect complexity to a read-only app. Cache preparation is the existing pipeline's job, not `yttoc-ask`'s. |
| Python preflight that error-exits on missing data | Python decides "you can't proceed." With the read-only approach, the LLM reports missing data to the user. |
| `get_xscript(video_id, section_path)` with path resolution | Python resolving section_path → {start, end} internally. The LLM already has boundaries from `get_summaries` — it can pass start/end directly. Thinner wrapper. |
| `get_summaries` returning filtered/reshaped data | §0 violation — designing a query-specific contract. Return the file verbatim. |
| Citation schema with `path` field | Bookkeeping the LLM doesn't need for reasoning. Python can reverse-lookup path from `{video_id, seconds}` via `summaries.json`. Thinner contract. |
| Separate `get_meta` tool | Redundant — `get_summaries` embeds `video: {id, title, url, ...}`. |
| Regex-based citation parsing in free text | Fragile with Japanese output. Structured Outputs are reliable. |
| Persist merged `sections.json` | Duplicates SRT content; risks drift. |
| Rich/TUI interactive REPL | Out of scope for v1. |

## 7. LLM Provider and Module Placement

### 7.1 Provider Decision

The current yttoc dependency is `openai`. **v1 uses the `openai` SDK** — no new dependency. Implementation target: **Responses API** (OpenAI's recommended API for new tool-use implementations).

### 7.2 Module Placement (nbdev)

**Common functions** (public, reusable across CLIs):

| Function | Module | Replaces / wraps |
|----------|--------|-----------------|
| `get_summaries(video_id, root) -> dict` | `summarize.py` | `map.py:load_summaries()` loop body; returns `summaries.json` verbatim |
| `get_xscript_range(video_id, start, end, root) -> list[dict]` | `xscript.py` | `parse_xscript()` + `slice_segments()`; returns raw `[{start, end, text}]` |

**New notebook and module:**

- `nbs/06_ask.ipynb` → `yttoc/ask.py`
- Exports:
  - `TOOLS`: tool schemas in OpenAI format (wrapping the 2 common functions above)
  - `ask(question, video_ids, model, max_iterations) -> dict`: Responses API loop → `{answer, citations}`
- CLI entry: `yttoc-ask` in `pyproject.toml`

**Tests:**

- `get_summaries`: fixture cache with a `summaries.json` file. Deterministic, no LLM.
- `get_xscript_range`: fixture cache with a `captions.<lang>.srt` file. Deterministic, no LLM. `root` parameter enables fixtures outside `~/.cache/yttoc/`. (No `summaries.json` needed — `start`/`end` are passed directly as arguments.)
- `ask()` loop: `#| eval: false` (requires API key).

## 8. Open Questions

1. **Streaming:** Structured Outputs return complete JSON. Streaming the answer text progressively may improve perceived latency. *Recommendation:* v1 buffers; streaming is a v2 optimization.
2. **Tool-call visibility:** Show the LLM's tool-use trace behind `--verbose`. Off by default.
3. **Multi-turn:** *Recommendation:* one-shot v1; shell users can reinvoke.

## 9. Non-Goals

- Cache preparation (handled by `yttoc-fetch` → `yttoc-toc` → `yttoc-sum`)
- Real-time transcript ingestion
- Replacing `yttoc-find` (keyword recall vs. conceptual questions are different needs)
- Sub-section sentence-level citations (`find_quote` tool) — v1 uses section-level
