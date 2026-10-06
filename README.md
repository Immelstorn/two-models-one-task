# two-models-one-task

Let two AI coding agents, for example Claude Code and Codex, work on one task together. They plan
together, split the work by what each does best, and review each other's work.

They talk through one shared file, `DIALOGUE.md`, using a small helper, `duo.py`. The helper numbers and
timestamps every message, stops the agents from talking over each other, tracks what each one still has
to answer, and wakes the other agent when a new message arrives.

## Quick start

1. Copy `duo.py` into your project root.
2. Open Claude Code and Codex in the project root, or start both at once with the
   [tmux shortcut](#both-sessions-in-one-terminal) below.
3. Paste the whole of [`START_PROMPT.md`](START_PROMPT.md) into each session, unchanged.
4. In **one** of the two, add your task right under the pasted prompt before sending, for example:
   `Task: add a Grafana dashboard for API latency, with tests.`
   The other session gets the prompt alone and picks the task up from the dialogue. You can also give
   the task later, to either session.

They agree on a plan, split the work by what each does best and review each other's parts. Watch
`DIALOGUE.md`; the agents tell you when a decision is yours and when the work is done.

Using other models? Edit the first line of `START_PROMPT.md` (`Participants: Claude and Codex`) once.

### Both sessions in one terminal

Run this in the project folder. It opens a tmux session with Claude Code on the left and Codex on the
right, both in that folder:

```bash
tmux new-session -s "duo-${PWD##*/}" -c "$PWD" \; send-keys 'claude' C-m \; split-window -h -c "$PWD" \; send-keys 'codex' C-m
```

To make it a `duo` command, add this line to `~/.zshrc` or `~/.bashrc`:

```bash
duo() { tmux new-session -s "duo-${PWD##*/}" -c "$PWD" \; send-keys 'claude' C-m \; split-window -h -c "$PWD" \; send-keys 'codex' C-m; }
```

- `Ctrl-b` then arrow keys moves between the panes. `Ctrl-b d` detaches; `tmux attach -t duo-<folder>`
  comes back. tmux turns dots in the folder name into `_`.
- Run it from a plain terminal, not from inside tmux.
- For top and bottom panes instead of side by side, change `-h` to `-v`.

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
| `next --as Claude` | Gives Claude every unanswered turn from Codex and records that Claude received it. |
| `append --as Claude --subject "..." --body reply.md --reply-to all` | Posts Claude's turn, then runs Codex's wake command if Codex has one. Refused if Codex posted something Claude has not read. |
| `wait --as Claude --timeout 3600` | Returns when Codex posts something new. Read-only. |
| `wake --as Codex --exec COMMAND` | Saves the command Claude runs after posting, to wake Codex. |
| `wake --as Codex --clear` | Removes Codex's wake command. |

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
