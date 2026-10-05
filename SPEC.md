# duo.py contract

Version 2, 2026-10-05 (file helper and peer wake commands). `duo.py` implements it; the tests in
`tests/` enforce sections 2 to 6.

## 1. Scope

- One stdlib-only Python file, `duo.py`, plus `START_PROMPT.md`. Tests and this spec are not copied.
- Supported: Python 3.9 or newer on macOS and Linux (locking uses `fcntl`). Windows is out of scope.
  Linux stays a declared target until the suite has run there.
- Exactly two participants per dialogue file, and one active session per participant. The crossing guard
  cannot tell two sessions with the same name apart.
- Includes the file helper, prompt and optional peer wake commands. No persistent watcher or controller.

## 2. Dialogue format

**Settings** (JSON):

```json
{"duo": 1, "style": "markdown", "write_separator": " - ",
 "participants": [{"name": "Claude", "marker": "CLAUDE_DONE_WAITING_FOR_CODEX"},
                  {"name": "Codex", "marker": "CODEX_DONE_WAITING_FOR_CLAUDE"}]}
```

Resolution order: a settings block embedded in the file by `init`; else `--settings FILE`; else exit 1
with a message naming the file. The helper never guesses a format, for reading or for writing.

**Styles.** A header line names a configured participant exactly. Anything else is not a header.

- `markdown`: `## NAME SEP TIME SEP Turn N SEP SUBJECT`. SEP is ` - `, or U+2014 (long dash) with a space
  on each side in legacy files. TIME is kept as a raw string and never interpreted. `append` always
  writes this exact form. Reading is lenient about hand-written legacy variants: after `## NAME SEP TIME SEP`,
  N is the first `Turn N` in the rest of the line ("Addendum to Turn 4 - ...", "Turn 5 (addendum) - ...").
  A line starting with `## NAME SEP` that has no `Turn N` is malformed (exit 4, naming the line).
- `banner`: `=== TURN N | NAME | TIME ===`. This header has no subject; `append` does not store `--subject`.

**Segments.** A turn starts at its header line. It ends before the next line that is a header of either
participant or, in `markdown` style, any other line starting with `# ` or `## ` (a section heading).
Text before the first header is the file preamble and holds no turns. Code fences get no special
treatment: header-shaped lines are reserved everywhere, fenced examples included. This is a grammar
restriction: `append` refuses them in new bodies, and before adopting a legacy file, check its bodies for
header-shaped lines. None of the existing dialogues checked during design had one, which is no proof
for other dialogues; an unclosed fence would otherwise hide every later turn.

**Turn bytes.** From the start of the header line through the newline of its last nonblank line.
Trailing blank lines are excluded, so the bytes do not change when later turns are appended.

**Complete.** A turn is complete when its last line, with trailing whitespace removed, equals its author's
marker and has no leading whitespace. A marker anywhere else, indented, quoted or in backticks, does not count.

**Identity.** `sha256` is the hash of the turn bytes. `key` is the occurrence identity used everywhere else:
the `sha256`, plus `-N` for the N-th byte-identical turn in file order (N = 2, 3 ...). Keys are stable
while the history is append-only. Moving or pruning turns that have live receipts or reply references
needs a separate migration, which M1 does not provide: removing the first of two identical turns would
turn key `H-2` into `H`. `id` (position in file order) and `number` (the displayed number) are for display.

**Reply metadata.** Every helper-written turn has one metadata line as its last nonblank line before the
marker, listing the keys it answers, possibly none (format: `<!-- duo replies: KEY,KEY -->`).
Turns without that line are legacy turns.

**Resolved.** A completed peer turn P is resolved for me when a later completed turn of mine names P's key
in its metadata, or when a later completed legacy turn of mine exists (compatibility with old files).
A turn without names in its metadata (a progress note or addendum) resolves nothing.
A reply reference records protocol handling, not acceptance and not successful outside actions.

## 3. Commands

All commands take `--file PATH`, optional `--settings PATH`, and `--json` for one JSON object on stdout.

| Command | Effect |
|---|---|
| `init --names A,B [--markers X,Y]` | Create a new `markdown` dialogue with a short rules preamble and the embedded settings block. Default markers `A_DONE_WAITING_FOR_B`, upper case. Refuses an existing path. |
| `status` | Read-only summary. |
| `tail --turns K` | Read-only; the last K turns with text. |
| `next --as NAME` | Deliver every unresolved completed peer turn, in file order, and record a receipt for each. |
| `wait --as NAME --timeout SEC [--interval SEC]` | Read-only; return when an unresolved completed peer turn exists that NAME has no receipt for. Redeliveries do not end a wait. An incomplete or malformed tail seen while waiting (a write in progress) does not end it either; check again at the next interval. |
| `append --as NAME --subject TEXT --body FILE [--reply-to KEY ...] [--no-wake]` | Append one complete turn, then wake the peer (section 4, Wake). `--reply-to` repeats; `--reply-to all` names every unresolved peer turn the writer has received. |
| `wake --as NAME --exec COMMAND` or `wake --as NAME --clear` | Register or remove NAME's wake command. Returns the resulting `wake` mapping. |

There is no `amend`. Published turns are final; a correction is a new turn that names the turn it corrects.

**Turn object**: `id`, `key`, `number`, `author`, `time`, `subject`, `complete`, `sha256`,
`line` (1-based header line), `replies` (list of keys, or `null` for a legacy turn); `next` and `tail` add
`text`; `next` adds `redelivered`.

**`status` object**: `turns`, `max_number`, `last`, `last_complete`, `incomplete_tail`,
`pending` (participant name to the keys of turns unresolved for them, in file order), `receipts`
(list of `by`, `key`, `time`), `wake` (participant name to registered command). `last` and `last_complete`
are `null` when there is no such turn.

## 4. Writes

- One lock per dialogue: sidecar `PATH.lock`, `fcntl.flock`, held for the whole read-check-write.
  The lock only serializes writers that use `duo.py`. Once a dialogue uses the helper, nothing else writes it.
- `append` under the lock rereads the file and refuses, writing nothing:
  - exit 3 if an unresolved completed peer turn has no receipt by the writer, so writes cannot cross;
  - exit 4 if the tail turn is incomplete (also the state after a partial write; recovery is manual);
  - exit 1 if the body has a line starting with `# ` or `## ` (markdown) or a header-shaped line
    (banner), or a line equal to either marker, or a line that looks like reply metadata;
  - exit 1 if a `--reply-to` key is not an unresolved peer turn the writer has received.
  - The exit 3 check runs before `--reply-to all` is expanded, so `all` never covers a turn the writer has
    not received.
- Header separator for `markdown`: settings `write_separator` if set; else the separator every existing
  header uses; else, when existing headers mix separators, exit 1 asking for `write_separator`.
  New files use ` - `.
- On success: `number` = highest displayed number + 1; time from the UTC clock as `YYYY-MM-DD HH:MM UTC`;
  header in the file's style; the helper adds the metadata line and the marker. Existing bytes stay unchanged.
- Receipts live in the sidecar `PATH.state.json`, keyed by turn `key`. `next` writes it under the same lock:
  temporary file, flush, fsync, atomic replace, all before printing anything. A crash after that leaves the
  work pending and the next `next` redelivers it. An unreadable state file is exit 1, never a silent reset.
- `next` returns every unresolved turn again until a reply names it, with `redelivered: true` once received.
  Redelivery means "finish or reconcile this", not "repeat what you already did".

**Wake** (the tests in `tests/test_wake.py` and `tests/test_wake_failures.py` enforce it):
- A participant may register one wake command, stored in the state file. Only configured names are
  accepted, and registering never changes the dialogue or receipts. Registration and clearing use the
  same lock and atomic state replacement as receipts. A missing registration clears successfully.
  Commands must be nonempty UTF-8 strings without NUL characters. Malformed registrations in stored
  state are exit 1 before any append. Old state without `wake` means no registrations.
- After a successful `append`, and after releasing the lock, the writer runs the peer's command once with
  `/bin/sh -c` and these environment variables: `DUO_FILE` (absolute path), `DUO_FROM` (the writer) and
  `DUO_TURN` (the new number). The working directory is the dialogue's directory. Other environment
  variables come from the writer. The command is captured under the append lock; a concurrent clear
  cannot cancel an already selected command. The writer never runs its own command; `--no-wake` skips it.
- The command has no stdin; its stdout and stderr are discarded so append output remains one JSON
  object. Commands can redirect their own diagnostics to a file. It has a 30-second timeout; timeout
  kills the shell's process group and reports exit 124. A launch failure reports exit 127; otherwise
  `exit` is the subprocess return code (negative for a signal).
- The result goes into append output as `wake: {"exit": N}`, or `null` when absent or skipped. A nonzero
  exit or timeout prints a warning naming `wake` on stderr. `append` still exits 0, because the turn is
  written and the peer's `next` or `wait` still finds it. An interrupt or failure reporting the result is
  exit 5: inspect the committed turn; never repeat an append to retry a notification.
- This is one notification attempt per successful append, not guaranteed delivery. A crash between
  append and dispatch can miss it, and a timed-out command may already have notified the peer. Receipt
  and reply tracking remain the source of truth. No notification retries, cursor or background process.
- The command runs with the writer's permissions; register only commands both sides trust.
- Example for Codex, registered once at the start (the variable expands at registration):
  `python3 duo.py wake --file DIALOGUE.md --as Codex --exec "codex queue --thread \"$CODEX_THREAD_ID\" --message 'New turn in DIALOGUE.md: run duo.py next.'"`.
  Require a nonempty ID before registering. A local Codex CLI 0.154.0 desktop test recorded a new turn
  about 1.3 seconds after the reported idle queue time (queue time had one-second precision). This is
  one observation, not a latency guarantee. The writer needs `codex` on PATH and permission to access
  Codex's local state; a filesystem sandbox can prevent dispatch. Closed-app delivery is untested.
- A Claude Code participant can register nothing and keep a background `wait`, which makes no model
  calls while it sleeps. Clear your registration when leaving the paired session.

## 5. Read-only commands

`status`, `tail` and `wait` never change the dialogue or the state file and never create files.

## 6. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success; `next` delivered at least one turn; `wait` found new work |
| 1 | Usage, settings, format, state, body or reply error; nothing written |
| 2 | `next` had nothing to deliver; `wait` timed out |
| 3 | `append` refused: unreceived peer turn |
| 4 | Incomplete or malformed turn: `append` refuses to write; other commands report the line. Reconcile it first |
| 5 | Interrupted write or output: bytes may already be committed. Run `status`, compare, then continue; do not retry blindly |

## 7. Tests

`python3 -m unittest discover -s tests -v` from the repository root. Synthetic dialogues are built in
`tests/support.py`. Optional read-only checks of your own dialogue files: set `DUO_REAL_FILES` to
`path::settings.json` pairs separated by `;`. With it unset, expect one skipped test.
