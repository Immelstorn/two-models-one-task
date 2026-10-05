"""Waking the peer after a post (SPEC 3 wake, 4 Wake)."""

from __future__ import annotations

import sys
import time
import unittest

from support import DUO, DuoCase, sha

RECORDER = '''import os, sys
open(sys.argv[1], "a").write(os.environ.get("DUO_FROM", "") + " " + os.environ.get("DUO_TURN", "") + "\\n")
sys.exit(int(sys.argv[2]))
'''


class Wake(DuoCase):
    def setUp(self) -> None:
        super().setUp()
        self.path, self.common = self.new_dialogue()
        self.recorder = self.write("recorder.py", RECORDER)
        self.log = self.dir / "wake.log"

    def command(self, code: int = 0) -> str:
        return f'"{sys.executable}" "{self.recorder}" "{self.log}" {code}'

    def register(self, who: str, command: str) -> None:
        self.duo("wake", *self.common, "--as", who, "--exec", command, expect=0)

    def runs(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_a_post_runs_the_peer_wake_command_once(self):
        self.register("Bo", self.command())

        result = self.duo_json("append", *self.common, "--as", "Ada", "--subject", "question",
                               "--body", self.body("Question.\n"))

        self.assertEqual(self.runs(), ["Ada 1"])
        self.assertEqual(result["wake"]["exit"], 0)

    def test_the_writer_never_runs_its_own_wake_command(self):
        self.register("Ada", self.command())

        result = self.duo_json("append", *self.common, "--as", "Ada", "--subject", "question",
                               "--body", self.body("Question.\n"))

        self.assertEqual(self.runs(), [])
        self.assertIsNone(result["wake"])

    def test_no_wake_skips_the_command(self):
        self.register("Bo", self.command())

        self.duo("append", *self.common, "--as", "Ada", "--subject", "note", "--body",
                 self.body("Note.\n"), "--no-wake", expect=0)

        self.assertEqual(self.runs(), [])

    def test_a_failed_wake_keeps_the_turn_and_is_reported(self):
        self.register("Bo", self.command(code=1))

        done = self.duo("append", *self.common, "--as", "Ada", "--subject", "question",
                        "--body", self.body("Question.\n"), "--json")

        self.assertEqual(done.returncode, 0)
        self.assertEqual(self.duo_json("status", *self.common)["last"]["author"], "Ada")
        self.assertIn("wake", done.stderr)

    def test_clear_and_status(self):
        self.register("Bo", self.command())
        shown = self.duo_json("status", *self.common)["wake"]

        self.duo("wake", *self.common, "--as", "Bo", "--clear", expect=0)
        self.post(self.common, "Ada", "question", "Question.\n")

        self.assertEqual(shown, {"Bo": self.command()})
        self.assertEqual(self.duo_json("status", *self.common)["wake"], {})
        self.assertEqual(self.runs(), [])

    def test_registration_leaves_the_dialogue_alone(self):
        before = sha(self.path)

        self.register("Bo", self.command())
        refused = self.duo("wake", *self.common, "--as", "Nobody", "--exec", self.command())

        self.assertEqual(sha(self.path), before)
        self.assertEqual(refused.returncode, 1)

    def test_the_wake_command_runs_after_the_lock_is_released(self):
        received = self.dir / "received.json"
        self.register("Bo", f'"{sys.executable}" "{DUO}" next --file "{self.path}" --as Bo --json > "{received}"')
        start = time.monotonic()

        self.post(self.common, "Ada", "question", "Question.\n")

        self.assertLess(time.monotonic() - start, 20)
        self.assertIn('"number": 1', received.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
