# two-models-one-task 🤝

Two AI coding agents, one task. Claude Code and Codex (or any two models) plan together, split the work
by what each does best, and check each other's results.

They talk through a shared file, `DIALOGUE.md`, using a tiny helper, `duo.py`: numbered messages, no
talking over each other, nothing forgotten, and the other agent wakes up when it's its turn.

## 💡 Why

One agent tends to trust its own reasoning. A second one, with its own context, improves the plan and
re-runs the results. You get fewer mistakes, earlier. Two models can still both be wrong, but less often.

## 🚀 Quick start

**1. Install**

```bash
curl -fsSL https://raw.githubusercontent.com/Immelstorn/two-models-one-task/main/install.sh | bash
```

This puts duo in `~/.local/share/duo`, adds the `duo` skill to Claude Code and Codex, and the `duo`
launcher to `~/.local/bin`. Nothing is cloned into your folders.

**2. Start** in the apps you already use, both opened on the same project folder:

| Claude Code | Codex |
|---|---|
| `/duo add a latency dashboard, with tests` | `$duo add a latency dashboard, with tests` |

Giving the task to one of them is enough; the other picks it up from the dialogue. No task? They ask you.
Want a lens? Say it in plain words: `$duo lens skeptic: review the login flow`.

**3. Watch** `DIALOGUE.md`. They tell you when a decision is yours and when they're done.

**Update** by running the install line again, or `duo -u`. **Uninstall** with the same line ending in
`| bash -s -- --uninstall`.

## 🖥️ Or launch both from a terminal

If the installer printed a `PATH` line, add it to `~/.zshrc` or `~/.bashrc` and open a new terminal. Then:

```bash
duo "add a latency dashboard, with tests"
```

This opens tmux with Claude Code on the left and Codex on the right, both with your task.

**Pick the pair.** Agents help most when they differ. Choose them with `-l` and `-r`; add a lens, a way
of thinking, with `:lens`:

```bash
duo -l opus -r sonnet "task"            # two Claude models
duo -l opus -r opus "task"              # same model twice: builder and skeptic lenses are added
duo -l opus:security -r codex "task"    # your own lens for one side
duo -l codex -r codex/MODEL "task"      # two Codex models
```

A lens changes how an agent thinks, not what it may work on. Run `duo -h` for all options.
In tmux: `Ctrl-b` and an arrow key switches panes, `Ctrl-b d` detaches, `tmux attach -t duo-<folder>` returns.

## 📋 No install? Paste instead

1. Copy `duo.py` into your project root.
2. Put your task on the `Task:` line of [`START_PROMPT.md`](START_PROMPT.md).
   Pairing other models? Change its `Participants:` line too.
3. Paste the whole prompt into both Claude Code and Codex.

## ✅ Requirements

- macOS or Linux with Python 3.9+. No packages needed; tmux for the launcher.
- Claude Code and Codex installed and signed in. Both stay open while they work.
- Add `DIALOGUE.md.lock` and `DIALOGUE.md.state.json` to your `.gitignore`. The skill copies `duo.py`
  into the project; commit it or ignore it.
- The first time an agent works in a folder, it may ask you to trust it or approve a command. Answer in
  that agent's window.

## ⚙️ How it works

- **Numbered turns** that are never edited; a correction is a new turn.
- **No crossed messages:** an agent must read the other's latest turn before posting.
- **Nothing lost:** a turn stays pending until it's answered, even after a crash.
- **Free waiting:** after posting, Claude wakes Codex with `codex queue`. Claude itself waits in a
  background process that makes no model calls.
- **Labelled wake-ups:** they start with `duo:` and never carry your authority.

## ⚠️ Limits

- A closed session doesn't wake up, so keep both apps open.
- Two Codex sessions wake each other only if `codex queue` may run outside Codex's sandbox.
- A wake-up is one attempt; the dialogue file is always the source of truth.
- No Windows (the lock uses `fcntl`).

<details>
<summary>📖 Commands and files</summary>

The agents run these; you normally don't need to. All take `--file DIALOGUE.md`.

| Command | What it does |
|---|---|
| `status` | Turn count, last turn, what is pending for whom. |
| `next --as Claude` | Gives Claude every unanswered turn from Codex. |
| `append --as Claude --subject "..." --body reply.md --reply-to all` | Posts Claude's turn, then wakes Codex if it registered a wake command. |
| `wait --as Claude --timeout 3600` | Returns when Codex posts something new. |
| `wake --as Codex --exec COMMAND` | Saves the command that wakes Codex. `--clear` removes it. |

Wake commands run with the poster's permissions, so both sides must trust them.

| File | What it is |
|---|---|
| `duo.py` | The helper: one file, standard library only. |
| `START_PROMPT.md` | The protocol both agents follow. |
| `skill/` | The `duo` skill for Claude Code and Codex. |
| `install.sh` | Installs, updates or uninstalls duo. |
| `bin/duo` | The tmux launcher. |
| `SPEC.md` | The full contract `duo.py` meets. |
| `tests/` | `python3 -m unittest discover -s tests -v` |

</details>

## 📄 License

MIT. Keep the copyright line at the top of `duo.py`.
