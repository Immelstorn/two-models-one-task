# duo.py contract (draft for review)

Status: draft v2.1, 2026-10-05. Names marked *proposed* can still be amended
once; the behaviour in sections 2 to 6 is what the tests in `tests/` enforce.

## 1. Scope

- One stdlib-only Python file, `duo.py`, plus `START_PROMPT.md`. Tests and this spec are not copied.
- Supported: Python 3.9 or newer on macOS and Linux (locking uses `fcntl`). Windows is out of scope.
  Linux stays a declared target until the suite has run there.
- Exactly two participants per dialogue file, and one active session per participant. The crossing guard
  cannot tell two sessions with the same name apart.
- Milestone 1 is the file helper and the prompt. Session wake-up and any controller are later milestones.

## 2. Dialogue format

**Settings** (JSON, *proposed* field names):

```json
{"duo": 1, "style": "markdown", "write_separator": " - ",
 "participants": [{"name": "Ada", "marker": "ADA_DONE_WAITING_FOR_BO"},
                  {"name": "Bo", "marker": "BO_DONE_WAITING_FOR_ADA"}]}
```

Resolution order: a settings block embedded in the file by `init`; else `--settings FILE`; else exit 1
with a message naming the file. The helper never guesses a format, for reading or for writing.

**Styles.** A header line names a configured participant exactly. Anything else is not a header.

- `markdown`: `## NAME SEP TIME SEP Turn N SEP SUBJECT`. SEP is ` - `, or U+2014 (long dash) with a space
  on each side in legacy files. TIME is kept as a raw string and never interpreted.
- `banner`: `=== TURN N | NAME | TIME ===`.

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
marker, listing the keys it answers, possibly none (*proposed* format: `<!-- duo replies: KEY,KEY -->`).
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
| `wait --as NAME --timeout SEC [--interval SEC]` | Read-only; return when an unresolved completed peer turn exists that NAME has no receipt for. Redeliveries do not end a wait. |
| `append --as NAME --subject TEXT --body FILE [--reply-to KEY ...]` | Append one complete turn. `--reply-to` repeats; `--reply-to all` names every unresolved peer turn the writer has received. |

There is no `amend`. Published turns are final; a correction is a new turn that names the turn it corrects.

**Turn object** (*proposed*): `id`, `key`, `number`, `author`, `time`, `subject`, `complete`, `sha256`,
`line` (1-based header line), `replies` (list of keys, or `null` for a legacy turn); `next` and `tail` add
`text`; `next` adds `redelivered`.

**`status` object** (*proposed*): `turns`, `max_number`, `last`, `last_complete`, `incomplete_tail`,
`pending` (participant name to the keys of turns unresolved for them, in file order), `receipts`
(list of `by`, `key`, `time`). `last` and `last_complete` are `null` when there is no such turn.

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

## 5. Read-only commands

`status`, `tail` and `wait` never change the dialogue or the state file and never create files.

## 6. Exit codes (*proposed*)

| Code | Meaning |
|---|---|
| 0 | Success; `next` delivered at least one turn; `wait` found new work |
| 1 | Usage, settings, format, state, body or reply error; nothing written |
| 2 | `next` had nothing to deliver; `wait` timed out |
| 3 | `append` refused: unreceived peer turn |
| 4 | `append` refused: incomplete tail turn |

## 7. Tests

`python3 -m unittest discover -s tests -v` from the repository root. Synthetic dialogues are built in
`tests/support.py`. Optional read-only checks of your own dialogue files: set `DUO_REAL_FILES` to
`path::settings.json` pairs separated by `;`. With it unset, expect one skipped test.
