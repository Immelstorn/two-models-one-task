# Instructions for agents working on this repository

- This repository is public and generic. No committed file may name another project, its paths, data,
  people or agent codenames. Documentation examples use Claude and Codex; test fixtures use the neutral names Ada and Bo.
- The maintainers coordinate in a local `DIALOGUE.md` beside this file. It is ignored by git and never
  committed. Read its header first, then reply there to the latest completed peer turn; it is append-only.
- `duo.py` stays one stdlib-only file. `SPEC.md` is the contract; the tests in `tests/` enforce it.
- Commits: stage your own files by explicit path; never `git add -A` or `git add .`. One-line messages.
  Push `main` to `origin` after each commit. Never force-push.
