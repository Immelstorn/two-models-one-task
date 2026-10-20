"""One durable wake attempt per recipient until next acknowledges the batch."""
from __future__ import annotations

import importlib.util
import io
import json
import shlex
import subprocess
import sys
import time
from unittest.mock import patch

from support import DUO, DuoCase

spec = importlib.util.spec_from_file_location('duo_coalescing_under_test', DUO)
duo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(duo)


class WakeCoalescing(DuoCase):
    def setUp(self):
        super().setUp()
        self.path, self.common = self.new_dialogue()
        self.state_path = self.path.with_name(self.path.name + '.state.json')
        self.log = self.dir / 'pings'
        self.recorder = self.write('record.py', '''import os, sys
with open(sys.argv[1], "a") as f:
    f.write(os.environ["DUO_TURN"] + "\\n")
sys.exit(int(sys.argv[2]))
''')
        self.command = shlex.join([sys.executable, str(self.recorder), str(self.log), '0'])
        self.register()

    def register(self, command=None):
        self.duo('wake', *self.common, '--as', 'Bo', '--exec',
                 command or self.command, expect=0)

    def post_note(self, subject='note', *extra):
        return self.duo_json('append', *self.common, '--as', 'Ada', '--subject', subject,
                             '--body', self.body('Please check the latest work.\n'), *extra)

    def pings(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def status(self):
        return self.duo_json('status', *self.common)

    def test_ten_posts_queue_once_and_next_receives_the_whole_batch(self):
        first = self.post_note('first')
        for i in range(9):
            self.assertEqual(self.post_note(str(i))['wake'], {'skipped': 'pending_ack'})
        self.assertEqual(self.pings(), ['1'])
        self.assertEqual(self.status()['wake_pending'], {'Bo': first['turn']['key']})

        received = self.duo_json('next', *self.common, '--as', 'Bo')['turns']
        self.assertEqual([t['number'] for t in received], list(range(1, 11)))
        self.assertEqual(self.status()['wake_pending'], {})
        self.assertEqual(self.post_note('after ACK')['wake'], {'exit': 0})
        self.assertEqual(self.pings(), ['1', '11'])
        # A receipt, not a completed reply, releases the next notification.
        self.assertEqual(len(self.status()['pending']['Bo']), 11)

    def test_no_wake_notes_neither_claim_nor_release_the_slot(self):
        self.assertIsNone(self.post_note('silent first', '--no-wake')['wake'])
        self.assertEqual(self.status()['wake_pending'], {})
        self.assertEqual(self.post_note('notify')['wake'], {'exit': 0})
        self.assertIsNone(self.post_note('silent later', '--no-wake')['wake'])
        self.assertEqual(self.post_note('coalesced')['wake'], {'skipped': 'pending_ack'})
        self.assertEqual(self.pings(), ['2'])

    def test_read_only_commands_and_sender_next_do_not_ack_for_recipient(self):
        self.post_note()
        self.duo('status', *self.common, expect=0)
        self.duo('tail', *self.common, expect=0)
        self.duo('wait', *self.common, '--as', 'Bo', '--timeout', '0', expect=0)
        self.duo('next', *self.common, '--as', 'Ada', expect=2)
        self.assertEqual(self.post_note('again')['wake'], {'skipped': 'pending_ack'})
        self.assertEqual(self.pings(), ['1'])

    def test_same_registration_preserves_pending_clear_or_change_rearms(self):
        self.post_note()
        self.register()
        self.assertEqual(self.post_note('same registration')['wake'], {'skipped': 'pending_ack'})
        self.register(self.command + ' # new destination')
        self.assertEqual(self.post_note('changed registration')['wake'], {'exit': 0})
        self.duo('wake', *self.common, '--as', 'Bo', '--clear', expect=0)
        self.assertEqual(self.status()['wake_pending'], {})
        self.register()
        self.assertEqual(self.post_note('explicit recovery')['wake'], {'exit': 0})
        self.assertEqual(self.pings(), ['1', '3', '4'])

    def test_uncertain_failure_does_not_queue_again_until_ack(self):
        self.register(shlex.join([sys.executable, str(self.recorder), str(self.log), '1']))
        # The external command may queue successfully and then exit nonzero.
        self.assertEqual(self.post_note()['wake'], {'exit': 1})
        self.assertEqual(self.post_note('later')['wake'], {'skipped': 'pending_ack'})
        self.assertEqual(self.pings(), ['1'])
        self.duo('next', *self.common, '--as', 'Bo', expect=0)
        self.assertEqual(self.post_note('after ACK')['wake'], {'exit': 1})
        self.assertEqual(self.pings(), ['1', '3'])

    def test_reservation_save_failure_preserves_post_without_dispatch(self):
        args = duo.arguments(['append', *self.common, '--as', 'Ada', '--subject', 'note',
                              '--body', self.body('Work is saved.\n')])
        with patch.object(duo, 'save_state', side_effect=OSError('disk full')), \
                patch.object(duo.sys, 'stderr', io.StringIO()) as errors:
            result, code = duo.append_turn(args, self.path)
        self.assertEqual(code, 0)
        self.assertEqual(result['wake'], {'skipped': 'state_error'})
        self.assertIn('turn is committed', errors.getvalue())
        self.assertEqual(self.pings(), [])
        self.assertEqual(self.status()['turns'], 1)
        self.assertEqual(len(self.duo_json('next', *self.common, '--as', 'Bo')['turns']), 1)
        self.assertEqual(self.post_note('recovered')['wake'], {'exit': 0})

    def test_failed_ack_save_keeps_the_slot_reserved(self):
        first = self.post_note()
        before = self.state_path.read_bytes()
        args = duo.arguments(['next', *self.common, '--as', 'Bo'])
        with patch.object(duo, 'save_state', side_effect=OSError('disk full')):
            with self.assertRaises(duo.DuoError) as caught:
                duo.deliver(args, self.path)
        self.assertEqual(caught.exception.code, 5)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.status()['wake_pending'], {'Bo': first['turn']['key']})
        self.assertEqual(self.post_note('still pending')['wake'], {'skipped': 'pending_ack'})

    def test_bad_pending_state_is_rejected_before_append(self):
        first = self.post_note()
        original = json.loads(self.state_path.read_text())
        before = self.path.read_bytes()
        for value in ([], {'Nobody': first['turn']['key']}, {'Bo': []},
                      {'Bo': 'missing'}, {'Ada': first['turn']['key']}):
            with self.subTest(value=value):
                self.state_path.write_text(json.dumps(dict(original, wake_pending=value)))
                self.post(self.common, 'Ada', 'bad state', 'Work.\n', expect=1)
                self.assertEqual(self.path.read_bytes(), before)
        self.state_path.write_text(json.dumps(original))

    def test_slow_dispatch_coalesces_parallel_post_and_cannot_overwrite_later_ack(self):
        started, release = self.dir / 'started', self.dir / 'release'
        script = self.write('delayed.py', '''import os, pathlib, sys, time
started, release, log = map(pathlib.Path, sys.argv[1:])
if os.environ["DUO_TURN"] == "1":
    started.touch()
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() > deadline:
            sys.exit(1)
        time.sleep(.01)
with log.open("a") as f:
    f.write(os.environ["DUO_TURN"] + "\\n")
''')
        self.register(shlex.join([sys.executable, str(script), str(started), str(release), str(self.log)]))
        # First append is still dispatching while a second process posts and Bo reads.
        process = subprocess.Popen([sys.executable, str(DUO), 'append', *self.common,
                                    '--as', 'Ada', '--subject', 'slow first',
                                    '--body', self.body('First.\n', 'first.md'), '--json'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not started.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(started.exists())
            self.assertEqual(self.post_note('parallel')['wake'], {'skipped': 'pending_ack'})
            self.assertEqual(len(self.duo_json('next', *self.common, '--as', 'Bo')['turns']), 2)
            third = self.post_note('new batch')
            self.assertEqual(third['wake'], {'exit': 0})
            release.touch()
            output, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(json.loads(output)['wake'], {'exit': 0})
            self.assertEqual(self.status()['wake_pending'], {'Bo': third['turn']['key']})
            self.assertEqual(self.pings(), ['3', '1'])
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_sender_auto_registration_does_not_release_the_peer_slot(self):
        first = self.post_note()
        # Registering Ada must not reset Bo's outstanding ping, including on refresh.
        for thread in ('11111111-1111-1111-1111-111111111111',
                       '11111111-1111-1111-1111-111111111111',
                       '22222222-2222-2222-2222-222222222222'):
            result = self.duo('append', *self.common, '--as', 'Ada', '--subject', 'still working',
                              '--body', self.body('Update.\n'), '--json', expect=0,
                              env={'CODEX_THREAD_ID': thread})
            self.assertEqual(json.loads(result.stdout)['wake'], {'skipped': 'pending_ack'})
            self.assertEqual(self.status()['wake_pending'], {'Bo': first['turn']['key']})
        self.assertEqual(self.pings(), ['1'])
