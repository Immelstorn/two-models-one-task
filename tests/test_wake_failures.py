"""Wake delivery boundaries: durable posts, isolated output and bounded commands."""
from __future__ import annotations

import importlib.util
import io
import json
import shlex
import sys
import time
from unittest.mock import patch

from support import DUO, DuoCase

spec = importlib.util.spec_from_file_location('duo_wake_under_test', DUO)
duo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(duo)


class WakeFailures(DuoCase):
    def setUp(self):
        super().setUp()
        self.path, self.common = self.new_dialogue()

    def register(self, command, person='Bo'):
        return self.duo('wake', *self.common, '--as', person, '--exec', command, expect=0)

    def in_process_append(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(duo.sys, 'stdout', output), patch.object(duo.sys, 'stderr', errors):
            code = duo.main(['append', *self.common, '--as', 'Ada', '--subject', 'question',
                             '--body', self.body('Question.\n'), '--json'])
        return code, json.loads(output.getvalue()), errors.getvalue()

    def test_environment_and_command_output_do_not_corrupt_json(self):
        saved = self.dir / 'environment.json'
        script = self.write('environment.py', '''import json, os, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({k: os.environ[k] for k in ("DUO_FILE", "DUO_FROM", "DUO_TURN")}))
assert Path.cwd() == Path(os.environ["DUO_FILE"]).parent
assert sys.stdin.read() == ""
print("not JSON")
print("private command diagnostics", file=sys.stderr)
''')
        self.register(shlex.join([sys.executable, str(script), str(saved)]))
        done = self.post(self.common, 'Ada', 'question', 'Question.\n')
        self.assertEqual(json.loads(done.stdout)['wake'], {'exit': 0})
        self.assertEqual(done.stderr, '')
        self.assertEqual(json.loads(saved.read_text()), {'DUO_FILE': str(self.path.resolve()),
                                                       'DUO_FROM': 'Ada', 'DUO_TURN': '1'})

    def test_receipts_and_registrations_survive_each_others_writes(self):
        self.register('true')
        self.post(self.common, 'Ada', 'question', 'Question.\n')
        self.duo('next', *self.common, '--as', 'Bo', expect=0)
        before = self.duo_json('status', *self.common)
        self.register('true', 'Ada')
        self.duo('wake', *self.common, '--as', 'Bo', '--clear', expect=0)
        after = self.duo_json('status', *self.common)
        self.assertEqual(before['wake'], {'Bo': 'true'})
        self.assertEqual(before['receipts'], after['receipts'])
        self.assertEqual(after['wake'], {'Ada': 'true'})

    def test_refused_append_never_wakes_and_invalid_registration_preserves_state(self):
        mark = self.dir / 'should-not-exist'
        self.register('touch ' + shlex.quote(str(mark)))
        state = self.path.with_name(self.path.name + '.state.json')
        before = state.read_bytes()
        self.duo('wake', *self.common, '--as', 'Bo', '--exec', '   ', expect=1)
        self.duo('wake', *self.common, '--as', 'Bo', '--clear', '--exec', 'true', expect=1)
        self.assertEqual(before, state.read_bytes())
        self.post(self.common, 'Bo', 'peer request', 'Question.\n')
        self.post(self.common, 'Ada', 'crossing reply', 'Answer.\n', expect=3)
        self.assertFalse(mark.exists())

    def test_corrupt_wake_state_fails_before_appending(self):
        self.register('true')
        state = self.path.with_name(self.path.name + '.state.json')
        initial = json.loads(state.read_text())
        before = self.path.read_bytes()
        for wake in ([], {'Nobody': 'true'}, {'Bo': ''}, {'Bo': 5}, {'Bo': 'a\x00b'}):
            state.write_text(json.dumps(dict(initial, wake=wake)))
            self.post(self.common, 'Ada', 'refused', 'Question.\n', expect=1)
            self.assertEqual(self.path.read_bytes(), before)

    def test_timeout_kills_child_and_keeps_a_single_pending_turn(self):
        mark = self.dir / 'late-child'
        script = self.write('slow.py', 'import pathlib, sys, time\ntime.sleep(0.8)\npathlib.Path(sys.argv[1]).touch()\n')
        self.register(shlex.join([sys.executable, str(script), str(mark)]) + ' & wait')
        with patch.object(duo, 'WAKE_TIMEOUT', 0.2):
            code, result, errors = self.in_process_append()
        self.assertEqual(code, 0)
        self.assertEqual(result['wake'], {'exit': 124})
        self.assertIn('wake timed out', errors)
        time.sleep(0.9)
        self.assertFalse(mark.exists())
        status = self.duo_json('status', *self.common)
        self.assertEqual(status['turns'], 1)
        self.assertEqual(status['pending']['Bo'], [result['turn']['key']])

    def test_launch_failure_warns_without_losing_post(self):
        self.register('true')
        with patch.object(duo.subprocess, 'Popen', side_effect=OSError('injected launch failure')):
            code, result, errors = self.in_process_append()
        self.assertEqual(code, 0)
        self.assertEqual(result['wake'], {'exit': 127})
        self.assertIn('wake', errors)
        self.assertEqual(self.duo_json('status', *self.common)['turns'], 1)

    def test_missing_command_and_no_wake_are_explicit_in_output(self):
        self.register('duo-command-that-does-not-exist')
        first = self.duo_json('append', *self.common, '--as', 'Ada', '--subject', 'question',
                              '--body', self.body('Question.\n'))
        self.assertEqual(first['wake'], {'exit': 127})
        skipped = self.duo_json('append', *self.common, '--as', 'Ada', '--subject', 'note',
                                '--body', self.body('Note.\n'), '--no-wake')
        self.assertIsNone(skipped['wake'])
