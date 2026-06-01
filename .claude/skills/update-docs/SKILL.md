---
name: update-docs
description: Update README.md, CLAUDE.md, and .docs/architecture.md to reflect the current state of the codebase. Run this before committing agent, model, prompt, or orchestrator changes.
---

Update the project documentation to reflect the current state of the code. Follow these steps:

1. Run `git diff HEAD` and `git status` to understand what has changed since the last commit.

2. Read the files that changed — focus on `agents/`, `models/`, `prompts/`, `orchestrator/`, `services/`.

3. Update the three documentation files as needed:

   **README.md**
   - Keep the "What it does" step list accurate
   - Keep the data flow diagram in sync with the pipeline
   - Keep the project structure tree accurate (files added/removed)
   - Keep the Roadmap table accurate (mark items Done when implemented, add new Planned items)
   - Update example output if the output format changed

   **CLAUDE.md**
   - Keep Session state code block in sync with `orchestrator/session.py`
   - Keep Data models section in sync with `models/`
   - Keep Pipeline section in sync with `orchestrator/pipeline.py`
   - Keep "What is not yet implemented" list accurate — remove items that are done
   - Keep File layout reference in sync with the actual directory structure
   - Keep Design principles accurate — add new ones only if a genuinely new invariant was introduced

   **.docs/architecture.md**
   - Add a new decision entry if a significant design choice was made that isn't already documented
   - A decision is worth documenting if it answers "why did we do it this way instead of the obvious alternative?"
   - Do not add entries for straightforward implementation details

4. Do not rewrite sections that are still accurate. Edit only what has actually changed.

5. Do not update CLAUDE.local.md — it contains role and collaboration preferences, not implementation state.
