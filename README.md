# two-models-one-task

A small harness for two AI coding agents (for example Claude Code and Codex, or two sessions of the same
tool) that work on one task together. They talk through one shared dialogue file: one implements, the
other reviews, and neither can overwrite or cross the other's messages.

**Status:** the file helper, starting prompt and optional peer wake commands are implemented. A writer
can notify an idle peer after posting, without a polling process on the receiving side.

## What you copy into a project

1. `duo.py`: one Python file, standard library only, Python 3.9 or newer on macOS or Linux. It numbers,
   timestamps and appends turns under a lock, delivers the other agent's turns, tracks which ones were
   answered, waits for new ones and runs a peer's registered wake command after posting.
2. `START_PROMPT.md`: the prompt each agent gets at the start of its session.

## How to use it

1. Copy `duo.py` into your project root.
2. Open two sessions in the project root, for example Claude Code and Codex, and paste the whole of
   `START_PROMPT.md` into each, unchanged. Pairing other models? Edit its first line (`Participants:`) once.
3. Give the task to one of them. That one implements; the other reviews.
4. Watch `DIALOGUE.md`. Step in when an agent says a decision is yours.

Add `DIALOGUE.md.lock` and `DIALOGUE.md.state.json` to your `.gitignore`; they are runtime files.

The core commands, all with `--file DIALOGUE.md`:

| Command | What it does |
|---|---|
| `status` | Turn count, last turn, what is pending for whom. Read-only. |
| `next --as Ada` | Gives Ada every unanswered turn from Bo and records that Ada received it. |
| `append --as Ada --subject "..." --body reply.md --reply-to all` | Posts Ada's turn. Refused if Bo posted something Ada has not received. |
| `wait --as Ada --timeout 3600` | Returns when Bo posts something new. Read-only. |
| `wake --as Ada --exec COMMAND` | Saves the command Bo will run after posting, to notify Ada. |
| `wake --as Ada --clear` | Removes Ada's wake command when the paired session stops. |

The starting prompt sets up Codex notification using `codex queue` when the session ID and writer's
host access are available. Claude Code can keep a background `wait` without idle model calls. Wake
commands run with the writer's permissions and must be trusted by both sides. The helper stops waiting
for a wake command after 30 seconds; failure leaves the turn posted and prints a warning. Do not post
the same turn again to retry a notification. Use `--no-wake` on an append that needs no peer action.

## Limits

- Keep the host applications open. An idle Codex task can receive a queued message; delivery with the
  app closed is untested. Claude Code's background wait needs its session to remain open. Without a
  usable wake or background-wait route, foreground waits return to the model on each timeout.
- Wake is one attempt after a post, not guaranteed delivery. A crash or failed command can miss the
  notification; the dialogue remains the source of truth. There is no daemon or automatic retry.
- One session per participant name, and nothing else may edit the dialogue file.
- Windows is not supported (the lock uses `fcntl`). Linux is supported but not yet tested there.

## Repository contents

| Path | Purpose |
|---|---|
| `duo.py` | The helper. |
| `START_PROMPT.md` | The shared starting prompt; only its participant names may need editing. |
| `SPEC.md` | The contract `duo.py` meets. |
| `tests/` | Acceptance tests: `python3 -m unittest discover -s tests -v`. |
| `AGENTS.md` | Rules for agents working on this repository. |
