# two-models-one-task

Let two AI coding agents, for example Claude Code and Codex, work on one task together. They plan
together, split the work by what each does best, and review each other's work.

They talk through one shared file, `DIALOGUE.md`, using a small helper, `duo.py`. The helper numbers and
timestamps every message, stops the agents from talking over each other, tracks what each one still has
to answer, and wakes the other agent when a new message arrives.

## Why two agents

One agent working alone tends to accept its own reasoning. A second agent, with its own context and its
own strengths, improves the plan, takes the parts it does better, and checks the other's work by
reproducing it. What reaches you is a plan that survived a second look and results that someone else
re-ran. That catches more mistakes early; it is not a guarantee that two models are right.

## Quick start

### Install once

Get the repository and make its `skill` folder a skill for both agents:

```bash
git clone https://github.com/Immelstorn/two-models-one-task ~/two-models-one-task
mkdir -p ~/.claude/skills ~/.agents/skills
ln -s ~/two-models-one-task/skill ~/.claude/skills/duo
ln -s ~/two-models-one-task/skill ~/.agents/skills/duo
```

### Start from the apps you already use

Open both agents on the same project folder: Claude Code in a terminal, its desktop app or an IDE, and
Codex. Both need the skill installed and access to that folder. Then type:

- in Claude Code: `/duo add a Grafana dashboard for API latency, with tests`
- in Codex: `$duo add a Grafana dashboard for API latency, with tests`

Giving the task to one of them is enough. The other can get just `/duo` or `$duo`: it may ask you for the
task, and takes it from the dialogue as soon as the first one posts it. Without any task, both ask you. You can add a lens or names in plain words,
for example `$duo lens skeptic: review the login flow`.

Tested so far: `/duo` in Claude Code and `$duo` in the Codex CLI. Codex documents skills in its desktop
app too, but `$duo` there has not been tested yet.

### Or start both from a terminal

The `duo` launcher opens tmux with both agents side by side and starts the skill in each. Put it on your
`PATH` once:

```bash
echo 'export PATH="$HOME/two-models-one-task/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
```

Then, in a new terminal, in any project folder:

```bash
duo "add a Grafana dashboard for API latency, with tests"
```

Claude Code opens on the left and Codex on the right, both with your task. Run `duo` without a task and
they ask you for one.

### Choosing the pair

Two agents help most when they differ. `-l` and `-r` pick the left and right agent: `claude`, `codex`,
or a Claude model such as `opus` or `sonnet`. Add `:lens` to give one a way of thinking, in plain words.

```bash
duo "task"                              # Claude Code + Codex
duo -l opus -r sonnet "task"            # two Claude models
duo -l opus -r opus "task"              # the same model twice: lenses builder and skeptic are added
duo -l opus:security -r codex "task"    # your own lens for one side
```

A lens shapes how an agent thinks, not which work it may take: a builder looks for the simplest thing
that works, a skeptic for what breaks. Different models differ more than different lenses; two copies
of one model with no lens tend to agree with each other. `duo -h` lists the options; `-d` starts the
session without attaching.

### Without installing anything

1. Copy `duo.py` into your project root.
2. Open Claude Code and Codex in the project root.
3. Copy [`START_PROMPT.md`](START_PROMPT.md) and put your task on its `Task:` line, for example
   `Task: add a Grafana dashboard for API latency, with tests.`
4. Paste the whole prompt into both sessions. If you leave the `Task:` line as it is, the agents ask
   you for the task.

Either way, the agents agree on a plan, split the work by what each does best and review each other's
parts. Watch `DIALOGUE.md`; they tell you when a decision is yours and when the work is done.

Using other models? Edit the first line of `START_PROMPT.md` (`Participants: Claude and Codex`) once.

### tmux tips

- `Ctrl-b` then an arrow key moves between the panes. `Ctrl-b d` detaches; `tmux attach -t duo-<folder>`
  comes back. tmux turns dots in the folder name into `_`.
- Inside tmux, `duo` switches to the new session instead of nesting it.
- A pane closes when its agent exits. Running `duo` again in the same folder while its session is open
  is refused; attach to it instead.

## What you need

- Python 3.9 or newer on macOS or Linux. Nothing else to install for `duo.py`; tmux and bash for the
  `duo` launcher.
- Claude Code and Codex installed and signed in, with a model that works on your account: the default
  one, or the one you pick with `-l` or `-r`.
- The first time an agent works in a folder, it may ask you to trust the folder or approve a command.
  Answer in that agent's window; the skill and the launcher never answer these for you.
- Both agent apps open while they work.
- These runtime files in your `.gitignore`: `DIALOGUE.md.lock` and `DIALOGUE.md.state.json`. The skill
  copies `duo.py` into the project root; commit it or ignore it as you prefer.

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
- **Wake-ups are labelled.** A wake message starts with `duo:`, so the receiving agent knows it comes from
  the other agent, not from you. It only means "check the dialogue" and grants no permission.

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
- Two Claude sessions each wait with a background `wait`, since Claude has no command to wake another
  session. Two Codex sessions would need `codex queue` outside the sandbox; untested.
- A wake is one attempt, not guaranteed delivery. The dialogue file is always the source of truth.
- One session per participant name, and nothing else may edit the dialogue file.
- Windows is not supported (the lock uses `fcntl`). Linux is untested.

## Repository

| Path | Purpose |
|---|---|
| `duo.py` | The helper: one file, standard library only. |
| `START_PROMPT.md` | The protocol both agents follow, ready to paste. |
| `skill/` | The `duo` skill for Claude Code and Codex: a short `SKILL.md` plus links to the two files above. |
| `bin/duo` | The launcher: opens both agents in tmux with the skill and your task. |
| `SPEC.md` | The full contract `duo.py` meets. |
| `tests/` | Acceptance tests: `python3 -m unittest discover -s tests -v`. |
| `AGENTS.md` | Rules for agents working on this repository. |
| `LICENSE` | MIT License. |

## License

MIT. See [LICENSE](LICENSE). You can use, change and share it freely; keep the copyright line that sits
at the top of `duo.py`.
