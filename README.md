# two-models-one-task

A small harness for two AI coding agents (for example Claude Code and Codex, or two sessions of the same
tool) that work on one task together. They talk through one shared dialogue file: one implements, the
other reviews, and neither can overwrite or cross the other's messages.

**Status:** milestone 1 is done: the file helper `duo.py` and the starting prompt. Waking an agent whose
session has ended is not part of it (see "Limits").

## What you copy into a project

1. `duo.py`: one Python file, standard library only, Python 3.9 or newer on macOS or Linux. It numbers,
   timestamps and appends turns under a lock, delivers the other agent's turns, tracks which ones were
   answered and waits for new ones.
2. `START_PROMPT.md`: the prompt each agent gets at the start of its session.

## How to use it

1. Copy `duo.py` into your project.
2. Fill the `{placeholders}` in `START_PROMPT.md` twice, once per agent: names, roles, task, dialogue
   path, your rules file, a session budget and a wait recipe for that agent's host.
3. Start two sessions and paste one filled prompt into each. The first agent creates the dialogue with
   `python3 duo.py init --file DIALOGUE.md --names Ada,Bo`.
4. Watch the dialogue file. Step in when an agent says a decision is yours.

The core commands, all with `--file DIALOGUE.md`:

| Command | What it does |
|---|---|
| `status` | Turn count, last turn, what is pending for whom. Read-only. |
| `next --as Ada` | Gives Ada every unanswered turn from Bo and records that Ada received it. |
| `append --as Ada --subject "..." --body reply.md --reply-to all` | Posts Ada's turn. Refused if Bo posted something Ada has not received. |
| `wait --as Ada --timeout 3600` | Returns when Bo posts something new. Read-only. |

## Limits

- Both sessions must stay open. `wait` only helps an agent that is still running: Claude Code can run it
  as a background command and is resumed when it returns; Codex can await it in the foreground or use a
  scheduled task. Neither wakes a session that has ended.
- One session per participant name, and nothing else may edit the dialogue file.
- Windows is not supported (the lock uses `fcntl`). Linux is supported but not yet tested there.

## Repository contents

| Path | Purpose |
|---|---|
| `duo.py` | The helper. |
| `START_PROMPT.md` | The starting prompt with placeholders. |
| `SPEC.md` | The contract `duo.py` meets. |
| `tests/` | Acceptance tests: `python3 -m unittest discover -s tests -v`. |
| `AGENTS.md` | Rules for agents working on this repository. |
