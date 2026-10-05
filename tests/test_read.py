"""Reading existing dialogues: formats, completion, identity and read-only behaviour (SPEC 2, 3, 5)."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from support import (ADDENDUM_HEADERS, BANNER_LEGACY, BANNER_SETTINGS, INCOMPLETE_TAIL, MARKDOWN_LEGACY,
                     MARKDOWN_SETTINGS, DuoCase, listing, sha)


class MarkdownLegacy(DuoCase):
    def setUp(self) -> None:
        super().setUp()
        self.path, self.common = self.legacy(MARKDOWN_LEGACY, MARKDOWN_SETTINGS)

    def test_status_reports_tail_and_counts(self):
        status = self.duo_json("status", *self.common)

        self.assertEqual(status["turns"], 4)
        self.assertEqual(status["max_number"], 3)
        self.assertEqual((status["last"]["id"], status["last"]["author"]), (4, "Ada"))
        self.assertTrue(status["last"]["complete"])
        self.assertFalse(status["incomplete_tail"])

    def test_long_dash_and_hyphen_headers_parse_alike(self):
        turns = self.duo_json("tail", *self.common, "--turns", "10")["turns"]

        self.assertEqual([(t["author"], t["number"]) for t in turns],
                         [("Ada", 1), ("Bo", 2), ("Ada", 3), ("Ada", 3)])
        self.assertEqual(turns[0]["subject"], "first question")
        self.assertEqual(turns[3]["subject"], "duplicate number, consecutive turn")

    def test_section_heading_ends_the_previous_turn(self):
        turns = self.duo_json("tail", *self.common, "--turns", "10")["turns"]

        self.assertTrue(turns[1]["complete"])
        self.assertNotIn("Recent exchange", turns[1]["text"])

    def test_preamble_and_quoted_markers_are_not_turns_or_completions(self):
        turns = self.duo_json("tail", *self.common, "--turns", "10")["turns"]

        self.assertEqual(turns[0]["line"], 10)
        self.assertTrue(all(t["complete"] for t in turns))

    def test_duplicate_numbers_and_consecutive_peer_turns_are_all_pending(self):
        status = self.duo_json("status", *self.common)
        turns = self.duo_json("tail", *self.common, "--turns", "10")["turns"]

        self.assertEqual(status["pending"]["Bo"], [turns[2]["key"], turns[3]["key"]])
        self.assertEqual(status["pending"]["Ada"], [])
        self.assertNotEqual(turns[2]["key"], turns[3]["key"])

    def test_unique_turns_use_their_hash_as_key_and_have_no_reply_metadata(self):
        turns = self.duo_json("tail", *self.common, "--turns", "10")["turns"]

        self.assertTrue(all(t["key"] == t["sha256"] and len(t["sha256"]) == 64 for t in turns))
        self.assertTrue(all(t["replies"] is None for t in turns))


class LegacyHeaderVariants(DuoCase):
    def test_words_around_the_turn_number_still_make_a_header(self):
        _, common = self.legacy(ADDENDUM_HEADERS, MARKDOWN_SETTINGS)

        turns = self.duo_json("tail", *common, "--turns", "10")["turns"]

        self.assertEqual([(t["author"], t["number"], t["complete"]) for t in turns],
                         [("Ada", 1, True), ("Bo", 1, True), ("Ada", 2, True)])

    def test_a_header_without_a_turn_number_is_reported(self):
        text = ADDENDUM_HEADERS.replace("Addendum to Turn 1 - one more point", "one more point")
        _, common = self.legacy(text, MARKDOWN_SETTINGS)

        done = self.duo("status", *common, "--json")

        self.assertEqual(done.returncode, 4)
        self.assertIn("line 10", done.stderr)


class BannerLegacy(DuoCase):
    def test_banner_status_and_pending(self):
        _, common = self.legacy(BANNER_LEGACY, BANNER_SETTINGS)

        status = self.duo_json("status", *common)
        turns = self.duo_json("tail", *common, "--turns", "5")["turns"]

        self.assertEqual(status["turns"], 2)
        self.assertEqual([(t["author"], t["number"], t["complete"]) for t in turns],
                         [("ADA", 1, True), ("BO", 2, True)])
        self.assertEqual(turns[1]["time"], "2026-10-02T15:40:00.123456+00:00")
        self.assertEqual(status["pending"]["ADA"], [turns[1]["key"]])


class IncompleteTail(DuoCase):
    def test_incomplete_tail_is_reported_apart_from_last_complete(self):
        _, common = self.legacy(INCOMPLETE_TAIL, MARKDOWN_SETTINGS)

        status = self.duo_json("status", *common)

        self.assertTrue(status["incomplete_tail"])
        self.assertEqual((status["last"]["number"], status["last"]["complete"]), (2, False))
        self.assertEqual((status["last_complete"]["number"], status["last_complete"]["author"]),
                         (1, "Ada"))
        self.assertEqual(status["pending"]["Ada"], [])


class Settings(DuoCase):
    def test_file_without_settings_is_an_error_and_unchanged(self):
        path = self.write("legacy.md", MARKDOWN_LEGACY)
        before = sha(path)

        done = self.duo("status", "--file", str(path), "--json")

        self.assertEqual(done.returncode, 1)
        self.assertIn("legacy.md", done.stderr)
        self.assertEqual(sha(path), before)


class ReadOnly(DuoCase):
    def test_status_tail_and_wait_change_nothing(self):
        path, common = self.legacy(MARKDOWN_LEGACY, MARKDOWN_SETTINGS)
        before_bytes, before_files = sha(path), listing(self.dir)

        self.duo("status", *common, "--json", expect=0)
        self.duo("tail", *common, "--turns", "2", "--json", expect=0)
        self.duo("wait", *common, "--as", "Bo", "--timeout", "1", expect=0)
        self.duo("wait", *common, "--as", "Ada", "--timeout", "1", expect=2)

        self.assertEqual(sha(path), before_bytes)
        self.assertEqual(listing(self.dir), before_files)
        self.assertEqual(self.duo_json("status", *common)["receipts"], [])


class OptionalRealFiles(DuoCase):
    """DUO_REAL_FILES="path::settings.json;path::settings.json" (read-only)."""

    def test_real_files_parse_read_only(self):
        pairs = [p for p in os.environ.get("DUO_REAL_FILES", "").split(";") if p]
        if not pairs:
            self.skipTest("DUO_REAL_FILES not set")
        for pair in pairs:
            dialogue, settings = (Path(p).resolve() for p in pair.split("::"))
            with self.subTest(dialogue=str(dialogue)):
                before, files = sha(dialogue), listing(dialogue.parent)

                status = self.duo_json("status", "--file", str(dialogue), "--settings", str(settings))

                self.assertGreater(status["turns"], 0)
                self.assertIsNotNone(status["last_complete"])
                self.assertEqual(sha(dialogue), before)
                self.assertEqual(listing(dialogue.parent), files)


if __name__ == "__main__":
    unittest.main()
