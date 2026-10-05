"""Additional failure/recovery checks, independent of the acceptance fixtures."""
from __future__ import annotations

import errno
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

from support import DuoCase, DUO, LONG_DASH_ONLY, MARKDOWN_SETTINGS, sha

spec = importlib.util.spec_from_file_location('duo_under_test', DUO)
duo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(duo)


class FailureRecovery(DuoCase):
    def test_receipt_exists_before_delivery_and_survives_output_failure(self):
        path, common = self.new_dialogue()
        self.post(common, 'Ada', 'request', 'Check this.\n')
        state = path.with_name(path.name + '.state.json')
        case = self

        class FailedOutput:
            def write(self, text):
                receipts = json.loads(state.read_text())['receipts']
                case.assertEqual(receipts[0]['by'], 'Bo')
                raise OSError(errno.ENOSPC, 'injected output failure')

        with patch.object(duo.sys, 'stdout', FailedOutput()), patch.object(duo.sys, 'stderr', io.StringIO()):
            code = duo.main(['next', *common, '--as', 'Bo', '--json'])
        self.assertEqual(code, 5)
        again = self.duo_json('next', *common, '--as', 'Bo')['turns']
        self.assertTrue(again[0]['redelivered'])
        self.assertEqual(len(self.keys(common, 'Bo')), 1)

    def test_failed_state_replace_preserves_receipts_and_cleans_temporary_file(self):
        path, common = self.new_dialogue()
        self.post(common, 'Ada', 'first request', 'Check this.\n')
        self.duo('next', *common, '--as', 'Bo', expect=0)
        state = path.with_name(path.name + '.state.json')
        before = state.read_bytes()
        self.post(common, 'Ada', 'second request', 'Also this.\n')
        with patch.object(duo.os, 'replace', side_effect=OSError('injected replace failure')):
            with patch.object(duo.sys, 'stderr', io.StringIO()):
                code = duo.main(['next', *common, '--as', 'Bo', '--json'])
        self.assertEqual(code, 5)
        self.assertEqual(state.read_bytes(), before)
        self.assertEqual(list(self.dir.glob('*.tmp')), [])
        again = self.duo_json('next', *common, '--as', 'Bo')['turns']
        self.assertEqual([t['redelivered'] for t in again], [True, False])

    def test_replaced_history_cannot_reuse_old_receipts(self):
        path, common = self.new_dialogue()
        self.post(common, 'Ada', 'first', 'Original request.\n')
        self.duo('next', *common, '--as', 'Bo', expect=0)
        path.write_bytes(path.read_bytes().replace(b'Original request.', b'Replaced request.'))
        before = sha(path)
        done = self.duo('next', *common, '--as', 'Bo', '--json', expect=1)
        self.assertIn('history changed', done.stderr)
        self.assertEqual(sha(path), before)

    def test_partial_header_is_not_skipped_when_appending(self):
        path, common = self.new_dialogue()
        self.post(common, 'Ada', 'first', 'Original request.\n')
        for fragment in (b'## A', b'## Ada - 2026-10-05 17:10 UTC - Tur'):
            original = path.read_bytes()
            path.write_bytes(original + b'\n' + fragment)
            before = sha(path)
            self.post(common, 'Ada', 'must not pass', 'Body.\n', expect=4)
            self.assertEqual(sha(path), before)
            path.write_bytes(original)

    def test_crlf_turn_keeps_its_exact_hash_after_append(self):
        path, common = self.legacy(LONG_DASH_ONLY, MARKDOWN_SETTINGS)
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        original = path.read_bytes()
        first = self.duo_json('next', *common, '--as', 'Bo')['turns'][0]
        self.post(common, 'Bo', 'reply', 'Done.\n', reply_to=('all',))
        turns = self.duo_json('tail', *common, '--turns', '2')['turns']
        self.assertEqual(turns[0]['sha256'], first['sha256'])
        self.assertTrue(path.read_bytes().startswith(original))

    def test_no_final_newline_is_rejected_without_changing_the_hash(self):
        path, common = self.legacy(LONG_DASH_ONLY.rstrip('\n'), MARKDOWN_SETTINGS)
        original = path.read_bytes()
        self.duo('next', *common, '--as', 'Bo', expect=0)
        self.post(common, 'Bo', 'reply', 'Done.\n', expect=1)
        self.assertEqual(path.read_bytes(), original)
