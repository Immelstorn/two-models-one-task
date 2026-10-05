# two-models-one-task

Let two AI coding agents work on one task together: one builds, the other reviews. For example, Claude
Code and Codex side by side.

They talk through one shared file, `DIALOGUE.md`, using a small helper, `duo.py`. The helper numbers and
timestamps every message, stops the agents from talking over each other, tracks what each one still has
to answer, and wakes the other agent when a new message arrives.

## Quick start

1. Copy `duo.py` into your project root.
2. Open Claude Code and Codex in the project root. Paste the whole of [`START_PROMPT.md`](START_PROMPT.md)
   into each, unchanged. There is nothing to fill in.
3. Tell one of them the task. That one builds; the other reviews.

Then watch `DIALOGUE.md`. The agents tell you when a decision is yours and when the work is done.

Using other models? Edit the first line of `START_PROMPT.md` (`Participants: Claude and Codex`) once.

## What you need

- Python 3.9 or newer on macOS or Linux. Nothing to install.
- Both agent apps open while they work.
- These runtime files in your `.gitignore`: `DIALOGUE.md.lock` and `DIALOGUE.md.state.json`.

## How it works

- **Turns.** Every message is a numbered turn with a UTC time and an end marker. Published turns are
  never edited; a correction is a new turn.
- **No crossed messages.** An agent cannot post while the other has posted something it has not read yet.
- **Nothing gets lost.** A turn stays pending until a reply names it. After a crash or restart, the agent
  gets its unanswered turns again.
- **Waking up costs nothing while idle.**
  - When Claude posts, `duo.py` runs the wake command Codex registered at startup (`codex queue`). On the
    Codex desktop app this started a new Codex turn within seconds.
  - Claude waits with a background `duo.py wait`: a sleeping process that makes no model calls.

## Commands

All commands take `--file DIALOGUE.md`. The agents run them; you normally don't need to.

| Command | What it does |
|---|---|
| `status` | Turn count, last turn, what is pending for whom. Read-only. |
| `next --as Ada` | Gives Ada every unanswered turn from Bo and records that Ada received it. |
| `append --as Ada --subject "..." --body reply.md --reply-to all` | Posts Ada's turn, then runs Bo's wake command if Bo has one. Refused if Bo posted something Ada has not received. |
| `wait --as Ada --timeout 3600` | Returns when Bo posts something new. Read-only. |
| `wake --as Ada --exec COMMAND` | Saves the command Bo runs after posting, to wake Ada. |
| `wake --as Ada --clear` | Removes Ada's wake command. |

Wake commands run with the poster's permissions, so both sides must trust them. A wake that fails or
takes over 30 seconds prints a warning; the turn is still posted. Use `--no-wake` for notes that need no reply.

## Limits

- Keep both apps open. Waking a closed Codex app is untested, and nothing restarts a closed session.
- A wake is one attempt, not guaranteed delivery. The dialogue file is always the source of truth.
- One session per participant name, and nothing else may edit the dialogue file.
- Windows is not supported (the lock uses `fcntl`). Linux is untested.

## Repository

| Path | Purpose |
|---|---|
| `duo.py` | The helper: one file, standard library only. |
| `START_PROMPT.md` | The starting prompt both agents get. |
| `SPEC.md` | The full contract `duo.py` meets. |
| `tests/` | Acceptance tests: `python3 -m unittest discover -s tests -v`. |
| `AGENTS.md` | Rules for agents working on this repository. |
| `LICENSE` | MIT License. |

## License

MIT. See [LICENSE](LICENSE). You can use, change and share it freely; keep the copyright line that sits
at the top of `duo.py`.
