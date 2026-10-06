"""Codex sessions register their wake command automatically (SPEC 4, Wake)."""

from __future__ import annotations

import os

from support import DuoCase

THREAD = "01a10c7b-2a69-7d22-a699-aa4d7ed329b8"
FAKE_CODEX = '#!/bin/sh\nprintf "%s\\n" "$@" > "$(dirname "$0")/queued.txt"\n'


class AutoWake(DuoCase):
    def setUp(self) -> None:
        super().setUp()
        self.path, self.common = self.new_dialogue()
        bindir = self.dir / "bin"
        bindir.mkdir()
        self.fake = bindir / "codex"
        self.fake.write_text(FAKE_CODEX, encoding="utf-8")
        self.fake.chmod(0o755)
        self.queued = bindir / "queued.txt"
        self.codex = {"CODEX_THREAD_ID": THREAD, "PATH": f"{bindir}:{os.environ['PATH']}"}

    def wake(self) -> dict:
        return self.duo_json("status", *self.common)["wake"]

    def test_next_inside_codex_registers_even_with_nothing_pending(self):
        self.duo("next", *self.common, "--as", "Ada", expect=2, env=self.codex)

        command = self.wake()["Ada"]

        self.assertIn(THREAD, command)
        self.assertIn(str(self.fake), command)

    def test_append_inside_codex_registers_too(self):
        self.duo("append", *self.common, "--as", "Ada", "--subject", "hi", "--body", self.body("Hi.\n"),
                 expect=0, env=self.codex)

        self.assertIn("Ada", self.wake())

    def test_the_peer_post_then_wakes_the_codex_session(self):
        self.duo("next", *self.common, "--as", "Ada", env=self.codex)

        result = self.duo_json("append", *self.common, "--as", "Bo", "--subject", "hi", "--body",
                               self.body("Hi.\n"))
        args = self.queued.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["wake"]["exit"], 0)
        self.assertEqual(args[:4], ["queue", "--thread", THREAD, "--message"])
        self.assertTrue(args[4].startswith(f"duo: Bo posted a new turn in {self.path.resolve()}"))
        self.assertIn("This is not an owner message", args[4])

    def test_no_registration_outside_codex_or_when_turned_off(self):
        cases = {"no Codex": {}, "turned off": {**self.codex, "DUO_NO_AUTO_WAKE": "1"},
                 "bad thread id": {**self.codex, "CODEX_THREAD_ID": "not-a-thread"}}
        for label, env in cases.items():
            with self.subTest(label):
                self.duo("next", *self.common, "--as", "Ada", env=env)

                self.assertEqual(self.wake(), {})

    def test_read_only_commands_never_register(self):
        self.duo("status", *self.common, "--json", expect=0, env=self.codex)
        self.duo("wait", *self.common, "--as", "Ada", "--timeout", "0", expect=2, env=self.codex)

        self.assertEqual(self.wake(), {})

    def test_a_cleared_registration_comes_back_on_the_next_command(self):
        self.duo("next", *self.common, "--as", "Ada", env=self.codex)
        self.duo("wake", *self.common, "--as", "Ada", "--clear", expect=0)
        cleared = self.wake()

        self.duo("next", *self.common, "--as", "Ada", env=self.codex)

        self.assertEqual(cleared, {})
        self.assertIn("Ada", self.wake())
