# two-models-one-task

A small harness for two AI coding agents (for example Claude Code and Codex, or two sessions of the same
tool) that work on one task together. They talk through one shared dialogue file: one implements, the
other reviews, and neither can overwrite or cross the other's messages.

> **Status:** work in progress. The contract (`SPEC.md`), the acceptance tests (`tests/`) and the starting
> prompt (`START_PROMPT.md`) are drafted. `duo.py` is not written yet, so the harness cannot be used today.

## What you copy into a project

1. `duo.py`: one Python file, standard library only, Python 3.9 or newer on macOS or Linux. It numbers,
   timestamps and appends turns under a lock, delivers the other agent's turns, tracks which ones were
   answered and waits for new ones.
2. `START_PROMPT.md`: the prompt each agent gets at the start of its session.

## How to use it (once `duo.py` exists)

1. Copy `duo.py` into your project.
2. Fill the `{placeholders}` in `START_PROMPT.md` twice, once per agent: names, roles, task, dialogue
   path, your rules file and a wait recipe for that agent's host.
3. Start two sessions and paste one filled prompt into each.
4. Watch the dialogue file. Step in when an agent says a decision is yours.

## Repository contents

| Path | Purpose |
|---|---|
| `SPEC.md` | The contract `duo.py` must meet. |
| `START_PROMPT.md` | The starting prompt with placeholders. |
| `tests/` | Acceptance tests: `python3 -m unittest discover -s tests -v`. |
| `AGENTS.md` | Rules for agents working on this repository. |
