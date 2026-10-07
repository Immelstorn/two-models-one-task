"""Writing dialogues: init, append format, guards and locking (SPEC 3, 4, 6)."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import subprocess
import sys
import unittest

from support import (BANNER_LEGACY, BANNER_SETTINGS, BO_MARK, DASH, DUO, HYPHEN_WRITES, INCOMPLETE_TAIL,
                     LONG_DASH_ONLY, MARKDOWN_LEGACY, MARKDOWN_SETTINGS, DuoCase, header_time, sha)


class Init(DuoCase):
    def test_init_creates_a_self_describing_dialogue(self):
        path, common = self.new_dialogue()

        status = self.duo_json("status", *common)

        self.assertTrue(path.exists())
        self.assertEqual((status["turns"], status["last"], status["incomplete_tail"]), (0, None, False))
        self.assertIn(BO_MARK, path.read_text(encoding="utf-8"))

    def test_init_creates_a_self_ignoring_folder(self):
        path = self.dir / ".duo" / "DIALOGUE.md"

        self.duo("init", "--file", str(path), "--names", "Ada,Bo", expect=0)

        self.assertTrue(path.is_file())
        self.assertEqual((path.parent / ".gitignore").read_text(encoding="utf-8"), "*\n")

    def test_init_leaves_an_existing_folder_alone(self):
        folder = self.dir / "docs"
        folder.mkdir()

        self.duo("init", "--file", str(folder / "DIALOGUE.md"), "--names", "Ada,Bo", expect=0)

        self.assertFalse((folder / ".gitignore").exists())

    def test_init_refuses_an_existing_file(self):
        path = self.write("dialogue.md", "keep me\n")

        done = self.duo("init", "--file", str(path), "--names", "Ada,Bo")

        self.assertEqual(done.returncode, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "keep me\n")


class Append(DuoCase):
    def test_append_writes_a_complete_turn_with_clock_time(self):
        path, common = self.new_dialogue()
        prefix = path.read_bytes()

        self.post(common, "Ada", "first question", "Please check the table.\n")
        last = self.duo_json("status", *common)["last"]

        self.assertEqual((last["author"], last["number"], last["subject"]), ("Ada", 1, "first question"))
        self.assertTrue(last["complete"])
        self.assertEqual(last["replies"], [])
        self.assertLess(abs((datetime.now(timezone.utc) - header_time(last)).total_seconds()), 120)
        self.assertTrue(path.read_bytes().startswith(prefix))

    def test_new_markdown_header_uses_hyphens(self):
        path, common = self.new_dialogue()

        self.post(common, "Ada", "hyphen check", "Body.\n")

        headers = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("## Ada")]
        self.assertEqual(len(headers), 1)
        self.assertRegex(headers[0], r"^## Ada - \d{4}-\d\d-\d\d \d\d:\d\d UTC - Turn 1 - hyphen check$")

    def test_append_to_legacy_files_keeps_bytes_and_style(self):
        cases = [("markdown", MARKDOWN_LEGACY, HYPHEN_WRITES, "Bo", r"^## Bo - .* - Turn 4 - reply$"),
                 ("long dash", LONG_DASH_ONLY, MARKDOWN_SETTINGS, "Bo",
                  rf"^## Bo {DASH} .* {DASH} Turn 2 {DASH} reply$"),
                 ("banner", BANNER_LEGACY, BANNER_SETTINGS, "ADA", r"^=== TURN 3 \| ADA \| .* ===$")]
        for index, (style, text, settings, who, header) in enumerate(cases):
            with self.subTest(style=style):
                path, common = self.legacy(text, settings, f"legacy-{index}.md")
                prefix = path.read_bytes()

                self.duo("next", *common, "--as", who, expect=0)
                self.post(common, who, "reply", "Done.\n", reply_to=("all",))
                last = self.duo_json("status", *common)["last"]

                self.assertTrue(path.read_bytes().startswith(prefix))
                self.assertEqual((last["author"], last["complete"]), (who, True))
                self.assertTrue(any(re.match(header, l) for l in path.read_text(encoding="utf-8").splitlines()))

    def test_mixed_legacy_separators_need_an_explicit_choice(self):
        path, common = self.legacy(MARKDOWN_LEGACY, MARKDOWN_SETTINGS)
        self.duo("next", *common, "--as", "Bo", expect=0)
        before = sha(path)

        done = self.post(common, "Bo", "reply", "Done.\n", expect=1)

        self.assertIn("write_separator", done.stderr)
        self.assertEqual(sha(path), before)

    def test_number_follows_the_highest_displayed_number(self):
        _, common = self.legacy(MARKDOWN_LEGACY, HYPHEN_WRITES)

        self.duo("next", *common, "--as", "Bo", expect=0)
        self.post(common, "Bo", "after duplicates", "Reply.\n")

        self.assertEqual(self.duo_json("status", *common)["last"]["number"], 4)

    def test_append_is_refused_until_the_peer_turn_is_received(self):
        path, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")
        before = sha(path)

        self.post(common, "Bo", "crossed", "Not read yet.\n", expect=3)
        unchanged = sha(path) == before
        self.duo("next", *common, "--as", "Bo", expect=0)
        self.post(common, "Bo", "answer", "Read and answered.\n", reply_to=("all",))

        self.assertTrue(unchanged)
        self.assertEqual(self.duo_json("status", *common)["last"]["author"], "Bo")

    def test_consecutive_own_turns_are_allowed(self):
        _, common = self.new_dialogue()

        self.post(common, "Ada", "question", "Question.\n")
        self.post(common, "Ada", "correction to turn 1", "Correction.\n")

        self.assertEqual(self.duo_json("status", *common)["turns"], 2)

    def test_append_is_refused_on_an_incomplete_tail(self):
        path, common = self.legacy(INCOMPLETE_TAIL, MARKDOWN_SETTINGS)
        before = sha(path)

        self.post(common, "Ada", "next", "Body.\n", expect=4)

        self.assertEqual(sha(path), before)

    def test_bodies_that_break_parsing_are_refused(self):
        path, common = self.new_dialogue()
        before = sha(path)
        bodies = ["## A heading\n", "# Title\n", "```\n## Fenced example\n```\n",
                  f"Text\n{BO_MARK}\nmore\n", "Text\nADA_DONE_WAITING_FOR_BO\n",
                  "Text\n<!-- duo replies: abc -->\n"]

        for index, text in enumerate(bodies):
            with self.subTest(body=text):
                self.post(common, "Ada", f"bad {index}", text, expect=1)

        self.assertEqual(sha(path), before)

    def test_turn_hash_is_stable_after_later_appends(self):
        _, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")
        first = self.duo_json("status", *common)["last"]

        self.duo("next", *common, "--as", "Bo", expect=0)
        self.post(common, "Bo", "answer", "Answer.\n", reply_to=("all",))
        turns = self.duo_json("tail", *common, "--turns", "5")["turns"]

        self.assertEqual((turns[0]["sha256"], turns[0]["key"]), (first["sha256"], first["key"]))

    def test_concurrent_appends_get_distinct_numbers(self):
        _, common = self.new_dialogue()
        writers = [subprocess.Popen(
            [sys.executable, str(DUO), "append", *common, "--as", "Ada", "--subject", f"note {i}",
             "--body", self.body(f"Note {i}.\n", f"note-{i}.md")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for i in range(12)]

        codes = [w.wait(timeout=60) for w in writers]
        turns = self.duo_json("tail", *common, "--turns", "50")["turns"]

        self.assertEqual(codes, [0] * 12)
        self.assertEqual(sorted(t["number"] for t in turns), list(range(1, 13)))
        self.assertTrue(all(t["complete"] for t in turns))


if __name__ == "__main__":
    unittest.main()
