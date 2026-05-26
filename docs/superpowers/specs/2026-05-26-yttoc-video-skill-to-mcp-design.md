# yttoc-video Skill to MCP Migration Design

**Date:** 2026-05-26
**Status:** Draft
**Author:** Hiroshi Doyu (with Codex)

## Background

The user frequently watches YouTube videos through `yttoc` using this manual
workflow:

```bash
vid=$(yttoc-fetch <url>)
yttoc-sum "$vid"
yttoc-txt "$vid"   # transcript text, given to LLM for further discussion
```

If Japanese output is needed, the LLM translates or explains the resulting
summary/transcript. This workflow is useful but still requires the user or LLM
to remember which CLI command to call and when to avoid overloading context with
full transcripts. Long transcripts may exceed the LLM context window (see Open
Questions).

The repository now has a minimal MCP server in `nbs/09_serve.ipynb` /
`yttoc/serve.py` exposing `get_date` as a smoke-test tool. That proves the
transport works, but the actual yttoc video workflow should not be MCP-ized
before the desired LLM behavior is validated.

## Core Decision

Use a **Skill-first, MCP-second** migration.

Stage 1 uses a Codex skill to encode the current CLI workflow and observe how
the LLM actually uses it on real videos. Stage 2 turns the repeated, stable
operations discovered in Stage 1 into MCP tools. This avoids designing tool
APIs before the usage pattern is clear.

## Goals

- Let the user provide a YouTube URL and get a useful yttoc-based summary with
  minimal prompting.
- Keep full transcript retrieval deliberate because it can be large.
- Preserve the current CLI pipeline while learning the right MCP API.
- Add only the MCP tools that prove useful in real use.
- Keep translation and explanation in the LLM layer, not in yttoc or MCP tools.

## Non-goals

- Do not add playlist support in this work.
- Do not add RAG or vector search.
- Do not add browser-opening behavior.
- Do not make MCP tools responsible for translation.
- Do not design CLI fallback into the final MCP skill until Stage 2 proves it is
  necessary.
- Do not expose a large set of speculative MCP tools.

## Existing Building Blocks

| Layer | Existing primitive | Notes |
| --- | --- | --- |
| CLI | `yttoc-fetch <url>` | Fetches captions and metadata; prints `video_id` |
| CLI | `yttoc-sum <video_id>` | Generates/prints summaries; may call LLM |
| CLI | `yttoc-txt <video_id> [section]` | Prints transcript text; can be long |
| Python | `get_video_info(url)` | Returns yt-dlp metadata |
| Python | `fetch_video(url, info, root=None)` | Saves cache and returns video dir |
| Python | `generate_summaries(video_id, root=None, refresh=False)` | Returns `AssembledSummaries` |
| Python | `parse_xscript(path)` | Returns parsed transcript segments |
| Python | `_render_txt(meta, segments, section, sec_info)` | Existing renderer, currently private |
| MCP | `get_date(utc=False)` | Smoke-test tool in `yttoc.serve` |

## Stage 0: MCP Smoke Test Baseline

Status: complete enough.

The `get_date` tool is intentionally simple. It should remain while yttoc MCP
tools are being added because it provides a quick way to verify that the MCP
server is registered and callable from Codex or Claude Code.

Acceptance:

- `yttoc MCP get_date` can be called from Codex.
- `nbdev-test --path nbs/09_serve.ipynb` passes.
- `mcp` remains an optional dependency (`pip install -e ".[mcp]"`).

No further feature work should be done in Stage 0.

## Stage 1: Skill-first Experiment

### Purpose

Create a local skill that teaches Codex the current yttoc CLI workflow. This
skill is a temporary operating layer and an API discovery tool.

### Skill Location

Create the skill under the Claude Code personal skills directory and symlink it
for Codex so both LLMs share the same source:

```bash
# Source of truth
~/.claude/skills/yttoc-video/SKILL.md

# Symlink for Codex
ln -s ~/.claude/skills/yttoc-video ~/.codex/skills/yttoc-video
```

The skill does not need bundled scripts at first. It should be concise and rely
on existing `yttoc-*` commands.

Verify that Codex discovers the symlinked skill before validation begins:
start a new Codex session and confirm `yttoc-video` appears in the available
skills list.

### Skill Trigger

The skill should trigger when the user asks Codex to process, summarize,
inspect, translate, or discuss a YouTube video using yttoc, especially when the
input includes a YouTube URL.

### Skill Behavior

Default workflow:

```bash
cd /home/doyu/yttoc
vid=$(.venv/bin/yttoc-fetch <url>)
.venv/bin/yttoc-sum "$vid"
```

Use `yttoc-txt` only when:

- the user explicitly asks for transcript text,
- the summary is insufficient for a follow-up question,
- exact wording is needed,
- a section-specific transcript is requested.

The skill should avoid pasting full transcripts into the answer unless the user
explicitly asks for that much text.

If Japanese output is requested:

- run the same yttoc commands,
- then have the LLM explain or translate the relevant result into Japanese.

The skill should include the `video_id` in its response so the user can continue
with explicit commands later.

### Minimal Skill Body Sketch

```markdown
---
name: yttoc-video
description: Use when the user gives a YouTube URL or video ID and wants yttoc-based fetching, summaries, transcripts, Japanese explanation, or follow-up discussion over the video.
---

# yttoc-video

Use existing yttoc CLI commands. Prefer summary first; avoid full transcript
unless needed.

1. Work from `/home/doyu/yttoc` and call repo-local entry points:
   `vid=$(.venv/bin/yttoc-fetch <url>)`
2. Run:
   `.venv/bin/yttoc-sum "$vid"`
3. Use `.venv/bin/yttoc-txt "$vid"` only when transcript detail is needed.
4. If Japanese is requested, translate/explain the retrieved content yourself.
5. Include the `video_id` and useful next commands in the response.
```

### Stage 1 Validation Matrix

Run the skill on at least three real videos:

| Case | User request | Expected behavior |
| --- | --- | --- |
| Summary only | "Summarize this YouTube URL with yttoc" | Fetch, summarize, return concise result and `video_id` |
| Transcript needed | "Use yttoc and tell me the exact wording around X" | Fetch/summarize first, then use transcript only as needed |
| Japanese explanation | "この動画をyttocで見て日本語で説明して" | Fetch/summarize, then answer in Japanese |

### What to Observe

- Does the LLM naturally need URL-based tools or video-id-based tools?
- Does it repeatedly call `yttoc-txt` too early?
- Are section-specific transcripts needed often?
- Does the user mostly want full summaries, section summaries, or exact quotes?
- Is the output too long?
- Which command sequence repeats across tasks?

### Stage 1 Completion Criteria

- The skill handles the three validation cases without manual command coaching.
- The repeated operations are clear enough to propose no more than two initial
  MCP tools.
- Any need for section or max-length transcript controls is documented.

## Stage 2: MCP API Design After Skill Validation

Do not finalize the MCP API before Stage 1. The current candidates are only
working hypotheses.

### Candidate Tool Set A: URL-first

Use this if most user interactions start from a fresh URL.

```python
yttoc_summary_from_url(url: str) -> str
yttoc_transcript_from_url(url: str, section: str = "", max_chars: int = 12000) -> str
```

Pros:

- Matches the user's natural request.
- Minimizes LLM orchestration.
- Good for one-off videos.

Cons:

- Fetching and summarizing are bundled, so the tool hides intermediate state.
- Repeated follow-up on cached videos may refetch/check cache each time.

### Candidate Tool Set B: Explicit cache primitives

Use this if Stage 1 shows frequent follow-up by `video_id`.

```python
yttoc_fetch_url(url: str) -> dict
yttoc_summary(video_id: str) -> str
yttoc_transcript(video_id: str, section: str = "") -> str
```

Pros:

- Makes cache state explicit.
- Better for multi-turn work on one video.
- Closer to existing CLI and Python primitives.

Cons:

- More tools.
- Requires more LLM orchestration.

### Initial Bias

Start with a summary-first API unless Stage 1 proves otherwise:

```python
yttoc_summary_from_url(url: str) -> str
```

Add transcript tooling only if Stage 1 shows it is repeatedly needed. If it is
added, prefer a bounded interface rather than a full-transcript default:

```python
yttoc_transcript_from_url(url: str, section: str = "", max_chars: int = 12000) -> str
```

Add video-id tools only when they remove real repetition.

### MCP Implementation Rules

- Implement in nbdev style:
  - source: `nbs/09_serve.ipynb`
  - generated module: `yttoc/serve.py`
- Use direct Python APIs, not subprocess.
- Keep tool return values simple strings at first.
- Keep translation outside MCP.
- Keep `get_date` until yttoc tools are stable.
- Add focused tests for pure helpers and smoke tests for server registration.

### Likely Python API Gaps

Summary is already available through `generate_summaries(...)`.

Transcript needs a small public helper because `yttoc_txt` currently prints
rather than returning a string. Add this only when Stage 2 begins.

Candidate helper:

```python
def get_txt(video_id: str, section: str = "", root: str | Path = None) -> str:
    "Return transcript text for a cached video."
```

This helper should reuse existing loading/rendering logic instead of duplicating
transcript formatting.

## Stage 3: Decide Whether the Skill Remains

Do not implement fallback now.

After Stage 2, decide one of:

| Outcome | Action |
| --- | --- |
| MCP tools are enough | Delete or archive the skill |
| MCP tools need usage guidance | Keep a very thin skill that tells Codex which MCP tool to call |
| CLI remains useful outside MCP | Keep the skill as a CLI workflow guide |

Avoid building a combined MCP/CLI fallback skill unless real use proves it is
needed.

## Implementation Plan

### Task 1: Create a tracking issue

Create a GitHub issue for this migration because it spans multiple sessions and
LLMs.

Suggested title:

```text
Prototype yttoc-video skill before MCP migration
```

The issue should link to this design document and track:

- Stage 1 skill creation,
- three-video validation,
- MCP API decision,
- Stage 2 implementation decision.

### Task 2: Create the `yttoc-video` skill

Create the skill and symlink per the Skill Location section above:

```bash
~/.claude/skills/yttoc-video/SKILL.md       # source of truth
ln -s ~/.claude/skills/yttoc-video ~/.codex/skills/yttoc-video
```

Keep it short. Do not add scripts or references initially.

Include:

- trigger description for YouTube URL / yttoc requests,
- summary-first workflow,
- transcript restraint rule,
- Japanese explanation rule,
- `video_id` reporting rule.
- explicit `/home/doyu/yttoc/.venv/bin/...` or `cd /home/doyu/yttoc` command
  usage.

Before validation, confirm the skill appears in Codex's available skills list.

### Task 3: Validate on three videos

For each validation run, leave a short GitHub issue comment:

- request used,
- commands run,
- whether transcript was needed,
- whether output was too long,
- what the future MCP tool should have been.

The design document should only be updated with durable conclusions, not every
session log.

### Task 4: Decide MCP API

After three videos, choose one:

- URL-first summary-only API,
- explicit cache primitive API,
- hybrid, only if there is clear evidence.

Record the decision as a GitHub issue comment. Update this design document only
if the chosen API differs from the candidates described above.

### Task 5: Implement MCP tools

Only after Task 4:

1. Add any missing public helper, likely in `nbs/02_xscript.ipynb`.
2. Update `nbs/09_serve.ipynb`.
3. Run:

```bash
.venv/bin/python scripts/normalize_notebooks.py nbs/*.ipynb
.venv/bin/nbdev-export
.venv/bin/nbdev-test --path nbs/09_serve.ipynb
.venv/bin/nbdev-test --n_workers 0
```

4. Register/restart MCP clients as needed.

### Task 6: Retire or shrink the skill

After MCP validation, decide whether the skill remains.

If it remains, it should be a thin usage guide, not a duplicate
implementation.

## Open Questions

- Should transcript MCP tools return full text, section text, or require a
  `max_chars` limit?
- Do users more often start from a URL or from cached `video_id`?
- Should `yttoc_summary_from_url` return Markdown exactly as the CLI does, or a
  compact structured string?
- Is `get_date` worth keeping permanently as MCP smoke test?
- Can LLMs reliably consume full `yttoc-txt` output for long videos, or does
  truncation occur? Stage 1 should observe whether transcript output gets cut
  off and whether section-level retrieval is needed to stay within context.

## Current Recommendation

Start Stage 1 now. Do not add yttoc MCP tools until the skill has been used on
three real videos and the repeated operations are obvious.
