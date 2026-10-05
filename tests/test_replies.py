"""Delivery, receipts, reply tracking, recovery and wait (SPEC 2 Resolved, 3, 4, 5)."""

from __future__ import annotations

import subprocess
import sys
import time
import unittest

from support import ADA_MARK, IDENTICAL, MARKDOWN_LEGACY, MARKDOWN_SETTINGS, DUO, DuoCase, listing, sha


class Next(DuoCase):
    def test_next_delivers_all_pending_turns_in_order_with_text(self):
        _, common = self.legacy(MARKDOWN_LEGACY, MARKDOWN_SETTINGS)

        delivered = self.duo_json("next", *common, "--as", "Bo")["turns"]

        self.assertEqual([(t["number"], t["subject"]) for t in delivered],
                         [(3, "hyphen header"), (3, "duplicate number, consecutive turn")])
        self.assertIn("Addendum.", delivered[1]["text"])
        self.assertFalse(any(t["redelivered"] for t in delivered))
        self.assertEqual([t["replies"] for t in delivered], [None, None])

    def test_next_with_nothing_pending_exits_2(self):
        _, common = self.new_dialogue()

        done = self.duo("next", *common, "--as", "Ada", "--json")

        self.assertEqual(done.returncode, 2)

    def test_status_shows_the_receipt(self):
        _, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")

        delivered = self.duo_json("next", *common, "--as", "Bo")["turns"]
        receipts = self.duo_json("status", *common)["receipts"]

        self.assertIn(("Bo", delivered[0]["key"]), [(r["by"], r["key"]) for r in receipts])


class Replies(DuoCase):
    def two_requests(self) -> tuple[list[str], list[str]]:
        _, common = self.new_dialogue()
        self.post(common, "Ada", "first fix", "Fix one.\n")
        self.post(common, "Ada", "second fix", "Fix two.\n")
        self.duo("next", *common, "--as", "Bo", expect=0)
        return common, self.keys(common, "Bo")

    def test_progress_post_resolves_nothing(self):
        common, keys = self.two_requests()

        self.post(common, "Bo", "working on the first fix", "Started.\n")
        again = self.duo_json("next", *common, "--as", "Bo")["turns"]

        self.assertEqual([t["key"] for t in again], keys)
        self.assertTrue(all(t["redelivered"] for t in again))

    def test_partial_reply_leaves_the_rest_pending(self):
        common, keys = self.two_requests()

        self.post(common, "Bo", "first fix done", "Done.\n", reply_to=(keys[0],))
        last = self.duo_json("status", *common)["last"]

        self.assertEqual(last["replies"], [keys[0]])
        self.assertEqual(self.keys(common, "Bo"), [keys[1]])

    def test_reply_to_all_resolves_everything_received(self):
        common, keys = self.two_requests()

        self.post(common, "Bo", "both fixes done", "Done.\n", reply_to=("all",))
        done = self.duo("next", *common, "--as", "Bo", "--json")

        self.assertEqual(self.duo_json("status", *common)["last"]["replies"], keys)
        self.assertEqual(done.returncode, 2)

    def test_reply_to_all_never_covers_an_unreceived_turn(self):
        common, _ = self.two_requests()
        self.post(common, "Ada", "third fix", "Fix three.\n")
        path = self.dir / "dialogue.md"
        before = sha(path)

        self.post(common, "Bo", "all done", "Done.\n", reply_to=("all",), expect=3)

        self.assertEqual(sha(path), before)
        self.assertEqual(len(self.keys(common, "Bo")), 3)

    def test_invalid_reply_keys_are_refused(self):
        common, keys = self.two_requests()
        self.post(common, "Bo", "first fix done", "Done.\n", reply_to=(keys[0],))
        own = self.duo_json("status", *common)["last"]["key"]
        path = self.dir / "dialogue.md"
        before = sha(path)

        for key in ("f" * 64, own, keys[0]):
            with self.subTest(key=key):
                self.post(common, "Bo", "bad reply", "Text.\n", reply_to=(key,), expect=1)

        self.assertEqual(sha(path), before)

    def test_identical_turns_have_distinct_keys_and_resolve_separately(self):
        _, common = self.legacy(IDENTICAL, MARKDOWN_SETTINGS)

        delivered = self.duo_json("next", *common, "--as", "Bo")["turns"]
        self.post(common, "Bo", "reran once", "Done.\n", reply_to=(delivered[0]["key"],))

        self.assertEqual(delivered[0]["sha256"], delivered[1]["sha256"])
        self.assertEqual(delivered[1]["key"], delivered[0]["sha256"] + "-2")
        self.assertEqual(self.keys(common, "Bo"), [delivered[1]["key"]])


class Wait(DuoCase):
    def test_wait_times_out_with_exit_2(self):
        _, common = self.new_dialogue()
        start = time.monotonic()

        done = self.duo("wait", *common, "--as", "Ada", "--timeout", "1", "--interval", "0.2")

        self.assertEqual(done.returncode, 2)
        self.assertLess(time.monotonic() - start, 10)

    def test_wait_returns_when_a_peer_turn_appears(self):
        _, common = self.new_dialogue()
        waiter = subprocess.Popen([sys.executable, str(DUO), "wait", *common, "--as", "Bo",
                                   "--timeout", "30", "--interval", "0.2"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(waiter.kill)
        time.sleep(1)

        self.post(common, "Ada", "question", "Question.\n")
        code = waiter.wait(timeout=15)

        self.assertEqual(code, 0)

    def test_wait_keeps_waiting_through_a_partial_write(self):
        path, common = self.new_dialogue()
        waiter = subprocess.Popen([sys.executable, str(DUO), "wait", *common, "--as", "Bo",
                                   "--timeout", "30", "--interval", "0.2"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(waiter.kill)
        time.sleep(1)

        with path.open("ab") as handle:
            handle.write(b"\n\n## Ada - 2026-10-05 17:30 UTC - Tur")
        time.sleep(1)
        with path.open("ab") as handle:
            handle.write(f"n 1 - question\n\nQuestion.\n\n{ADA_MARK}\n".encode())
        code = waiter.wait(timeout=15)

        self.assertEqual(code, 0)

    def test_wait_ignores_received_but_unresolved_turns(self):
        _, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")
        self.duo("next", *common, "--as", "Bo", expect=0)
        self.post(common, "Bo", "working on it", "Started.\n")

        done = self.duo("wait", *common, "--as", "Bo", "--timeout", "1", "--interval", "0.2")

        self.assertEqual(done.returncode, 2)
        self.duo("next", *common, "--as", "Bo", expect=0)


class State(DuoCase):
    def test_corrupt_state_is_an_error_not_a_reset(self):
        path, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")
        state = self.write(path.name + ".state.json", "{not json")

        done = self.duo("next", *common, "--as", "Bo", "--json")

        self.assertEqual(done.returncode, 1)
        self.assertEqual(state.read_text(encoding="utf-8"), "{not json")

    def test_read_only_commands_leave_existing_state_alone(self):
        path, common = self.new_dialogue()
        self.post(common, "Ada", "question", "Question.\n")
        self.duo("next", *common, "--as", "Bo", expect=0)
        state = path.with_name(path.name + ".state.json")
        before = (sha(path), sha(state), listing(self.dir))

        self.duo("status", *common, "--json", expect=0)
        self.duo("tail", *common, "--turns", "3", "--json", expect=0)
        self.duo("wait", *common, "--as", "Ada", "--timeout", "1", "--interval", "0.2", expect=2)

        self.assertEqual((sha(path), sha(state), listing(self.dir)), before)


if __name__ == "__main__":
    unittest.main()
