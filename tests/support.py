"""Shared helpers and synthetic dialogues for the duo.py acceptance tests."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DUO = ROOT / "duo.py"
DASH = "\u2014"  # long dash used by legacy markdown headers

ADA_MARK = "ADA_DONE_WAITING_FOR_BO"
BO_MARK = "BO_DONE_WAITING_FOR_ADA"
MARKDOWN_SETTINGS = {"duo": 1, "style": "markdown", "participants": [
    {"name": "Ada", "marker": ADA_MARK}, {"name": "Bo", "marker": BO_MARK}]}
HYPHEN_WRITES = {**MARKDOWN_SETTINGS, "write_separator": " - "}
BANNER_SETTINGS = {"duo": 1, "style": "banner", "participants": [
    {"name": "ADA", "marker": "ADA_FINISHED"}, {"name": "BO", "marker": "BO_FINISHED"}]}

# Legacy markdown: long-dash and hyphen headers, a standalone marker in the preamble,
# quoted and indented markers in a body, section headings, a duplicate number and
# two consecutive Ada turns.
MARKDOWN_LEGACY = f"""# Ada and Bo dialogue

End each turn with your marker, for example:
{ADA_MARK}

## Turn protocol

Append only.

## Ada {DASH} 2026-09-18 10:00 UTC {DASH} Turn 1 {DASH} first question

Please check the table.

{ADA_MARK}


## Bo {DASH} 2026-09-18 10:05 UTC {DASH} Turn 2 {DASH} reply

Checked. Your marker `{ADA_MARK}` is quoted here and indented below:
    {BO_MARK}

{BO_MARK}

## Recent exchange

## Ada - 2026-09-19 08:00 UTC - Turn 3 - hyphen header

Second question.

{ADA_MARK}


## Ada - 2026-09-19 08:01 UTC - Turn 3 - duplicate number, consecutive turn

Addendum.

{ADA_MARK}
"""

BANNER_LEGACY = """ADA / BO REVIEW DIALOGUE

PROTOCOL
End a turn with your token on its own line:
   ADA_FINISHED  or  BO_FINISHED
ADA_FINISHED

=== TURN 1 | ADA | 2026-10-02 17:24:19 CEST ===

First findings. I will wait for BO_FINISHED before replying.

ADA_FINISHED

=== TURN 2 | BO | 2026-10-02T15:40:00.123456+00:00 ===

Review done.

BO_FINISHED
"""

LONG_DASH_ONLY = f"""# Dialogue

## Ada {DASH} 2026-09-18 10:00 UTC {DASH} Turn 1 {DASH} question

Question.

{ADA_MARK}
"""

# Two byte-identical Ada turns, as an import of duplicated history can produce.
_SAME = f"""## Ada - 2026-09-18 10:10 UTC - Turn 2 - repeated request

Please rerun the check.

{ADA_MARK}
"""
IDENTICAL = f"""# Dialogue

## Bo - 2026-09-18 10:00 UTC - Turn 1 - start

Starting.

{BO_MARK}

{_SAME}
{_SAME}"""

# Hand-written legacy headers that put words around "Turn N".
ADDENDUM_HEADERS = f"""# Dialogue

## Ada - 2026-09-18 10:00 UTC - Turn 1 - question

Question.

{ADA_MARK}


## Bo - 2026-09-18 10:05 UTC - Addendum to Turn 1 - one more point

Point.

{BO_MARK}


## Ada - 2026-09-18 10:09 UTC - Turn 2 (addendum) - follow-up

More.

{ADA_MARK}
"""

# The tail turn quotes its marker mid-body but does not end with it.
INCOMPLETE_TAIL = f"""# Dialogue

## Ada - 2026-09-18 10:00 UTC - Turn 1 - question

Question.

{ADA_MARK}


## Bo - 2026-09-18 10:05 UTC - Turn 2 - still writing

{BO_MARK}
Draft continues after a marker line.
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def listing(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def header_time(turn: dict) -> datetime:
    return datetime.strptime(turn["time"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)


class DuoCase(unittest.TestCase):
    """Runs duo.py as a subprocess in a fresh temporary directory."""

    def setUp(self) -> None:
        self.assertTrue(DUO.exists(), f"duo.py not found at {DUO}")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def settings(self, data: dict, name: str = "dialogue.settings.json") -> Path:
        return self.write(name, json.dumps(data))

    def legacy(self, text: str, settings: dict, name: str = "legacy.md") -> tuple[Path, list[str]]:
        """A legacy dialogue file plus the common arguments to address it."""
        path = self.write(name, text)
        return path, ["--file", str(path), "--settings", str(self.settings(settings))]

    def new_dialogue(self) -> tuple[Path, list[str]]:
        path = self.dir / "dialogue.md"
        self.duo("init", "--file", str(path), "--names", "Ada,Bo", expect=0)
        return path, ["--file", str(path)]

    def duo(self, *args: str, expect: int | None = None) -> subprocess.CompletedProcess:
        done = subprocess.run([sys.executable, str(DUO), *args], capture_output=True,
                              text=True, cwd=self.dir, timeout=60)
        if expect is not None:
            self.assertEqual(done.returncode, expect,
                             f"duo {' '.join(args)}\nstdout: {done.stdout}\nstderr: {done.stderr}")
        return done

    def duo_json(self, *args: str, expect: int = 0) -> dict:
        return json.loads(self.duo(*args, "--json", expect=expect).stdout)

    def body(self, text: str, name: str = "body.md") -> str:
        return str(self.write(name, text))

    def post(self, common: list[str], who: str, subject: str, text: str, expect: int = 0,
             reply_to: tuple[str, ...] = ()):
        replies = [arg for key in reply_to for arg in ("--reply-to", key)]
        return self.duo("append", *common, "--as", who, "--subject", subject,
                        "--body", self.body(text, f"body-{who}-{subject}.md"), *replies, expect=expect)

    def keys(self, common: list[str], who: str) -> list[str]:
        return self.duo_json("status", *common)["pending"][who]
