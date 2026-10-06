---
name: duo
description: Work on one task together with another AI coding agent (Claude Code, Codex, or another Claude model) through a shared DIALOGUE.md file and the duo.py helper. Use when the owner invokes /duo or $duo, or asks you to work with codex, work with claude, or pair with another agent on something.
---

Read `START_PROMPT.md`, which sits next to this file, and follow it exactly.

- The text after `/duo` or `$duo` may start with `participants: A and B; you are X; lens: L.` The `duo`
  launcher writes it; the lens part is optional. If it is there, A and B replace the prompt's
  Participants line, in that order, X is your name and L is your lens. The owner may also give a
  partner, your name or a lens in plain words (for example `$duo lens skeptic: review the login flow`);
  use those the same way.
- The rest of that text is the task, usually after `Task:`. Use it as the prompt's Task line. If there is
  no task, treat the Task line as empty.
- `duo.py` also sits next to this file. If the project root has no `duo.py`, copy it there before step 1,
  so both agents run the same commands.
