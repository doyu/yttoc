# yttoc-sum original-language summaries design

Status: Implemented
Issue: https://github.com/doyu/yttoc/issues/39
Date: 2026-05-26

## Goal

`yttoc-sum` should generate summaries and keywords in the video's transcript language instead of always asking for English output.

The concrete problem in #39 is Japanese videos producing English summaries with Japanese evidence quotes. This mixes languages in one output and makes the summary less useful for language-native review.

## Decisions

- Scope: only `yttoc-sum` summary and keywords are changed.
- Out of scope: `yttoc-toc` section titles stay as they are for now.
- Language source: use the first key in `Meta.captions`.
- Ordering: this intentionally depends on Python dict insertion order. `fetch.py` writes the selected caption language first, so the first key represents the transcript language used by yttoc.
- Fallback: use `en` only when `Meta.captions` is empty.
- Evidence quotes: keep original transcript wording.
- Cache behavior: existing `summaries.json` is not invalidated automatically. Users run `yttoc-sum <id> --refresh` to regenerate with the new prompt.
- Translation: not handled by yttoc; translation remains an LLM-layer task.

## Pre-change code facts

- `Meta` does not have a `lang` field.
- `Meta.captions` stores caption language codes as keys, such as `{"ja": "auto"}`.
- `_build_summary_prompt()` currently hardcodes `English summary`.
- `SectionSummaryPayload.summary` currently describes the field as an English summary.
- `generate_summaries()` already supports `refresh=True`.

## Implementation Plan

1. Derive the summary language inside `_build_summary_prompt()`.
   - Use `next(iter(meta.captions), "en")`.
   - Keep this inline to avoid exposing a private helper in nbdev docs.

2. Update `_build_summary_prompt()`.
   - Add `Summary language: {lang}` to the video info block.
   - Replace `1-2 sentence English summary` with language-neutral wording.
   - Explicitly instruct the LLM to write summaries and keywords in the summary language.
   - Explicitly keep evidence quotes in the original transcript wording.

3. Update Pydantic field descriptions.
   - Remove English-only wording from `SectionSummaryPayload.summary`.
   - Clarify that keywords should use the requested language when natural.

4. Add tests in the notebook.
   - Existing English-caption prompt includes `Summary language: en`.
   - Japanese-caption prompt includes `Summary language: ja`.
   - Prompt no longer contains `English summary`.
   - Prompt contains the evidence-quote preservation instruction.

5. Export and verify.
   - `.venv/bin/python scripts/normalize_notebooks.py nbs/04_summarize.ipynb`
   - `.venv/bin/nbdev-export`
   - `.venv/bin/nbdev-test --path nbs/04_summarize.ipynb`
   - `.venv/bin/nbdev-test --n_workers 0`

## Verification

- `.venv/bin/nbdev-test --path nbs/04_summarize.ipynb`
- `.venv/bin/nbdev-test --n_workers 0`

## Non-goals

- Do not change `toc.py`.
- Do not change `NormalizedSection.title`.
- Do not add automatic prompt-version cache invalidation.
- Do not add translation options.
- Do not add new dependencies.
