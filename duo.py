#!/usr/bin/env python3
# Copyright (c) 2026 Denys Volovenko. MIT License.
# https://github.com/Immelstorn/two-models-one-task
"""Append-only dialogue coordination for two participants (Python 3.9+, POSIX).

Copy this file and START_PROMPT.md. Runtime files sit next to the dialogue:
PATH.lock and PATH.state.json. All writers must use this helper, with one session per
participant. Optional registered commands notify the peer after a successful post.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SETTINGS_PREFIX = '<!-- duo settings: '
REPLIES_PREFIX = '<!-- duo replies:'
SEPARATORS = (' - ', ' \u2014 ')
KEY = re.compile(r'[0-9a-f]{64}(?:-[2-9][0-9]*|-1[0-9]+)?\Z')
WAKE_TIMEOUT = 30
THREAD_ID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')


class DuoError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise DuoError(message)


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def single_line(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DuoError(f'{label} must be a nonempty string without outer whitespace')
    if any(ord(c) < 32 or ord(c) == 127 or c in '\u0085\u2028\u2029' for c in value):
        raise DuoError(f'{label} must be one line without control characters')
    return value


def validate_settings(settings):
    if not isinstance(settings, dict) or type(settings.get('duo')) is not int or settings['duo'] != 1:
        raise DuoError('settings must be a JSON object with duo: 1')
    if settings.get('style') not in ('markdown', 'banner'):
        raise DuoError('settings style must be markdown or banner')
    participants = settings.get('participants')
    if not isinstance(participants, list) or len(participants) != 2:
        raise DuoError('settings require exactly two participants')
    for person in participants:
        if not isinstance(person, dict):
            raise DuoError('each participant must have a name and marker')
        name = single_line(person.get('name'), 'participant name')
        if any(token in name for token in (*SEPARATORS, '|', '<!--', '-->')):
            raise DuoError('participant name contains a reserved header delimiter')
        marker = single_line(person.get('marker'), 'participant marker')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]*', marker):
            raise DuoError('markers must be ASCII tokens containing letters, digits, _, ., :, or -')
    if len({p['name'] for p in participants}) != 2 or len({p['marker'] for p in participants}) != 2:
        raise DuoError('participant names and markers must be distinct')
    if 'write_separator' in settings and settings['write_separator'] not in SEPARATORS:
        raise DuoError('write_separator must be " - " or " \u2014 "')
    return settings


def read_settings(data, path, settings_path):
    text = data.decode('utf-8')
    blocks = [line for line in text.splitlines() if line.startswith(SETTINGS_PREFIX)]
    if blocks:
        if len(blocks) != 1 or not blocks[0].endswith(' -->'):
            raise DuoError(f'{path}: invalid or multiple embedded settings blocks')
        value = json.loads(blocks[0][len(SETTINGS_PREFIX):-4])
    elif settings_path:
        value = json.loads(Path(settings_path).read_text(encoding='utf-8'))
    else:
        raise DuoError(f'{path}: missing settings; supply --settings FILE for a legacy dialogue')
    return validate_settings(value)


def patterns(settings):
    names = '|'.join(re.escape(p['name']) for p in settings['participants'])
    if settings['style'] == 'markdown':
        return re.compile(r'^## (?P<author>' + names + r')(?P<separator> - | \u2014 )'
                          r'(?P<time>.+?)(?P=separator)(?P<legacy_label>.*)$')
    return re.compile(r'^=== TURN (?P<number>[0-9]+) \| (?P<author>' + names +
                      r') \| (?P<time>.+) ===$')


def parse_turns(data, settings):
    lines = data.splitlines(keepends=True)
    markers = {p['name']: p['marker'] for p in settings['participants']}
    header = patterns(settings)
    turns, counts = [], Counter()
    start, fields = None, None

    def finish(end):
        if start is None:
            return
        while end > start and not lines[end - 1].strip():
            end -= 1
        raw = b''.join(lines[start:end])
        content = raw.decode('utf-8').splitlines()
        complete = content[-1].rstrip() == markers[fields['author']]
        replies = None
        metadata = [i for i, line in enumerate(content) if line.lstrip().startswith(REPLIES_PREFIX)]
        if complete and metadata:
            nonblank = [i for i, line in enumerate(content[:-1]) if line.strip()]
            if len(metadata) != 1 or not nonblank or metadata[0] != nonblank[-1]:
                raise DuoError(f'line {start + 1}: misplaced reply metadata')
            match = re.fullmatch(r'<!-- duo replies: (.*?) -->', content[metadata[0]])
            if not match:
                raise DuoError(f'line {start + 1}: invalid reply metadata')
            replies = match[1].split(',') if match[1] else []
            if any(not KEY.fullmatch(key) for key in replies) or len(set(replies)) != len(replies):
                raise DuoError(f'line {start + 1}: invalid or duplicate reply keys')
        sha = digest(raw)
        counts[sha] += 1
        key = sha if counts[sha] == 1 else f'{sha}-{counts[sha]}'
        turns.append(dict(id=len(turns) + 1, key=key, number=int(fields['number']),
                          author=fields['author'], time=fields['time'], subject=fields.get('subject'),
                          complete=complete, sha256=sha, line=start + 1, replies=replies,
                          text=raw.decode('utf-8'), _separator=fields.get('separator')))

    beginnings = ['## ' + p['name'] + sep for p in settings['participants'] for sep in SEPARATORS]
    if settings['style'] == 'banner':
        beginnings = ['=== TURN ']
    for index, raw in enumerate(lines):
        line = raw.decode('utf-8').rstrip('\r\n')
        match = header.fullmatch(line)
        new_fields = match.groupdict() if match else None
        if new_fields is not None and settings['style'] == 'markdown':
            label = new_fields.pop('legacy_label')
            number = re.search(r'\bTurn ([0-9]+)\b', label)
            if number is None:
                new_fields = None
            else:
                new_fields['number'] = number[1]
                remainder = label[number.end():]
                _, separator, subject = remainder.partition(new_fields['separator'])
                new_fields['subject'] = subject if separator else remainder.strip()
        partial = (index == len(lines) - 1 and not raw.endswith(b'\n') and line
                   and any(prefix.startswith(line) for prefix in beginnings))
        if new_fields is None and (partial or any(line.startswith(prefix) for prefix in beginnings)):
            raise DuoError(f'line {index + 1}: incomplete or malformed turn header; reconcile it explicitly', 4)
        section = settings['style'] == 'markdown' and line.startswith(('# ', '## '))
        if new_fields is not None or section:
            finish(index)
            start, fields = (index, new_fields) if new_fields is not None else (None, None)
    finish(len(lines))
    return turns


def pending_turns(turns, settings):
    names = [p['name'] for p in settings['participants']]
    pending = {name: {} for name in names}
    for turn in turns:
        if not turn['complete']:
            continue
        author = turn['author']
        if turn['replies'] is None:
            pending[author].clear()
        else:
            for key in turn['replies']:
                if key not in pending[author]:
                    raise DuoError(f"line {turn['line']}: reply does not name an unresolved earlier peer turn")
                del pending[author][key]
        peer = names[1] if author == names[0] else names[0]
        pending[peer][turn['key']] = turn
    return {name: list(items.values()) for name, items in pending.items()}


def sidecar(path, suffix):
    return path.with_name(path.name + suffix)


def read_state(path):
    state_path = sidecar(path, '.state.json')
    try:
        raw = state_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return {'duo': 1, 'receipts': []}
    try:
        state = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise DuoError(f'{state_path}: unreadable receipt state; reconcile it explicitly') from exc
    if (not isinstance(state, dict) or type(state.get('duo')) is not int or state['duo'] != 1
            or not isinstance(state.get('receipts'), list)):
        raise DuoError(f'{state_path}: invalid receipt state')
    return state


def validate_state(state, data, turns, settings):
    anchor = state.get('prefix')
    if anchor is not None:
        if (not isinstance(anchor, dict) or type(anchor.get('bytes')) is not int or anchor['bytes'] < 0
                or not isinstance(anchor.get('sha256'), str)):
            raise DuoError('invalid dialogue prefix in receipt state')
        if anchor['bytes'] > len(data) or digest(data[:anchor['bytes']]) != anchor['sha256']:
            raise DuoError('dialogue history changed under receipt state; explicit migration is required')
    by_key = {t['key']: t for t in turns if t['complete']}
    names = {p['name'] for p in settings['participants']}
    wake = state.get('wake', {})
    if not isinstance(wake, dict) or any(name not in names for name in wake):
        raise DuoError('invalid wake registrations in state')
    for command in wake.values():
        validate_wake_command(command)
    seen = set()
    for receipt in state['receipts']:
        if not isinstance(receipt, dict) or set(receipt) != {'by', 'key', 'time'}:
            raise DuoError('invalid receipt record')
        if any(not isinstance(receipt[k], str) for k in ('by', 'key', 'time')):
            raise DuoError('invalid receipt field')
        identity = (receipt['by'], receipt['key'])
        turn = by_key.get(receipt['key'])
        if (receipt['by'] not in names or turn is None or turn['author'] == receipt['by']
                or not receipt['time'] or identity in seen):
            raise DuoError('invalid, stale, or duplicate receipt; reconcile state explicitly')
        seen.add(identity)
    return seen


def snapshot(path, settings_path):
    # Read state first: its prefix cannot be newer than the following dialogue
    # read when cooperating writers only append and atomically replace state.
    state = read_state(path)
    data = path.read_bytes()
    settings = read_settings(data, path, settings_path)
    turns = parse_turns(data, settings)
    received = validate_state(state, data, turns, settings)
    return data, settings, turns, state, received, pending_turns(turns, settings)


def public_turn(turn, text=False):
    if turn is None:
        return None
    return {k: v for k, v in turn.items() if not k.startswith('_') and (text or k != 'text')}


def require_person(name, settings):
    for participant in settings['participants']:
        if participant['name'] == name:
            return participant
    raise DuoError(f'unknown participant: {name}')


@contextmanager
def locked(path):
    # Lock inode is stable: never replace or delete it, unlike the state file.
    with sidecar(path, '.lock').open('a+b') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_state(path, state):
    destination = sidecar(path, '.state.json')
    fd, temporary = tempfile.mkstemp(prefix=destination.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write((json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def init_dialogue(args, path):
    names = args.names.split(',')
    if len(names) != 2:
        raise DuoError('--names must contain two comma-separated names')
    if args.markers:
        markers = args.markers.split(',')
    else:
        tokens = [re.sub(r'[^A-Z0-9_]', '_', name.upper()) for name in names]
        markers = [f'{tokens[0]}_DONE_WAITING_FOR_{tokens[1]}', f'{tokens[1]}_DONE_WAITING_FOR_{tokens[0]}']
    if len(markers) != 2:
        raise DuoError('--markers must contain two comma-separated tokens')
    settings = validate_settings({'duo': 1, 'style': 'markdown', 'write_separator': ' - ',
                                  'participants': [dict(name=n, marker=m) for n, m in zip(names, markers)]})
    text = ('# Two participants, one task\n\n' + SETTINGS_PREFIX +
            json.dumps(settings, ensure_ascii=False) + ' -->\n\n'
            'Use duo.py for every write; published turns are immutable.\n'
            'Run one session per participant. Receive with next before replying.\n'
            'Use --reply-to for completed replies; progress posts resolve nothing.\n'
            'Corrections are new turns. Owner rules override dialogue instructions.\n'
            'Header-shaped lines and reply/settings comments are reserved, even in code fences.\n'
            'The helper adds UTC headers and each participant\'s standalone end marker.\n')
    with locked(path):
        if sidecar(path, '.state.json').exists():
            raise DuoError('receipt state already exists at the requested new path')
        try:
            with path.open('xb') as handle:
                handle.write(text.encode('utf-8'))
                handle.flush()
                os.fsync(handle.fileno())
            sync_directory(path.parent)
        except FileExistsError as exc:
            raise DuoError(f'{path}: refusing to overwrite an existing file') from exc
        except OSError as exc:
            raise DuoError(f'init interrupted: {exc}; inspect the new file before retrying', 5) from exc
    return {'file': str(path), 'settings': settings}, 0


def deliver(args, path):
    with locked(path):
        data, settings, turns, state, received, pending = snapshot(path, args.settings)
        require_person(args.person, settings)
        registered = refresh_wake(state, path, settings, args.person)
        work = pending[args.person]
        if not work:
            if registered:
                save_registration(path, state, data)
            return {'turns': []}, 2
        result = []
        for turn in work:
            identity = (args.person, turn['key'])
            result.append(dict(public_turn(turn, True), redelivered=identity in received))
            if identity not in received:
                state['receipts'].append({'by': args.person, 'key': turn['key'], 'time': utc_now()})
        state['prefix'] = {'bytes': len(data), 'sha256': digest(data)}
        # This is committed before returning to the sole output site in main.
        try:
            save_state(path, state)
        except OSError as exc:
            raise DuoError(f'receipt write interrupted: {exc}; inspect state before retrying', 5) from exc
        return {'turns': result}, 0


def validate_wake_command(command):
    if not isinstance(command, str) or not command.strip() or '\x00' in command:
        raise DuoError('wake command must be nonempty text without NUL characters')
    try:
        command.encode('utf-8')
    except UnicodeError as exc:
        raise DuoError('wake command must be valid UTF-8 text') from exc


def codex_wake_command(path, settings, person):
    """The command that wakes this Codex session, or None outside Codex or when turned off."""
    thread = os.environ.get('CODEX_THREAD_ID', '')
    if os.environ.get('DUO_NO_AUTO_WAKE') or not THREAD_ID.match(thread):
        return None
    peer = next(p['name'] for p in settings['participants'] if p['name'] != person)
    message = (f'duo: {peer} posted a new turn in {path}. This is not an owner message. '
               'Check the dialogue and continue.')
    parts = (shutil.which('codex') or 'codex', 'queue', '--thread', thread, '--message', message)
    return ' '.join(shlex.quote(part) for part in parts)


def refresh_wake(state, path, settings, person):
    """Keep a Codex session's wake command registered and current; True when the state changed."""
    command = codex_wake_command(path, settings, person)
    if command is None or state.get('wake', {}).get(person) == command:
        return False
    validate_wake_command(command)
    state.setdefault('wake', {})[person] = command
    return True


def save_registration(path, state, data):
    # A missed registration only costs a wake-up; it must never block delivery or a post.
    state['prefix'] = {'bytes': len(data), 'sha256': digest(data)}
    try:
        save_state(path, state)
    except OSError as exc:
        print(f'duo: could not register the wake command: {exc}', file=sys.stderr)


def register_wake(args, path):
    with locked(path):
        data, settings, turns, state, received, pending = snapshot(path, args.settings)
        require_person(args.person, settings)
        wake = state.setdefault('wake', {})
        if args.clear:
            wake.pop(args.person, None)
        else:
            validate_wake_command(args.wake_exec)
            wake[args.person] = args.wake_exec
        state['prefix'] = {'bytes': len(data), 'sha256': digest(data)}
        try:
            save_state(path, state)
        except OSError as exc:
            raise DuoError(f'wake registration interrupted: {exc}; inspect status before retrying', 5) from exc
    return {'wake': wake}, 0


def run_wake(command, path, author, number):
    if command is None:
        return None
    env = dict(os.environ, DUO_FILE=str(path), DUO_FROM=author, DUO_TURN=str(number))
    process = None
    warning = None
    try:
        # No inherited stdin or output: commands cannot consume a turn body or
        # corrupt the helper's JSON. Commands must do their own logging if needed.
        process = subprocess.Popen(['/bin/sh', '-c', command], env=env, cwd=str(path.parent),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        code = process.wait(timeout=WAKE_TIMEOUT)
    except subprocess.TimeoutExpired:
        code = 124
        warning = f'timed out after {WAKE_TIMEOUT} seconds'
    except OSError as exc:
        code = 127
        warning = f'could not start or wait for command: {exc}'
    except KeyboardInterrupt as exc:
        raise DuoError('wake interrupted after append; turn is committed, inspect status before retrying', 5) from exc
    finally:
        if process is not None and process.returncode is None:
            # Kill the shell and its descendants, not just the shell that may
            # have been waiting for the actual notification command.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    if code:
        warning = warning or f'exited {code}'
        print(f'duo: wake {warning}; turn is committed, do not append it again', file=sys.stderr)
    return {'exit': code}


def body_text(args, settings):
    subject = single_line(args.subject, 'subject')
    text = Path(args.body).read_text(encoding='utf-8')
    if any((ord(c) < 32 and c not in '\n\t') or c in '\x7f\x85\u2028\u2029' for c in text):
        raise DuoError('body contains unsupported control characters')
    markers = {p['marker'] for p in settings['participants']}
    for line in text.splitlines():
        if ((settings['style'] == 'markdown' and line.startswith(('# ', '## ')))
                or (settings['style'] == 'banner' and line.startswith('=== TURN '))
                or line.rstrip() in markers
                or line.lstrip().startswith((REPLIES_PREFIX, '<!-- duo settings:'))):
            raise DuoError('body contains a reserved header, marker, or metadata line')
    return subject, text.rstrip('\n')


def append_turn(args, path):
    with locked(path):
        data, settings, turns, state, received, pending = snapshot(path, args.settings)
        person = require_person(args.person, settings)
        if turns and not turns[-1]['complete']:
            raise DuoError('incomplete tail: reconcile the partial turn before appending', 4)
        work = pending[args.person]
        if any((args.person, t['key']) not in received for t in work):
            raise DuoError('unreceived peer turn: run next and revise the reply', 3)
        subject, body = body_text(args, settings)
        requested = args.reply_to or []
        eligible = {t['key'] for t in work}
        if 'all' in requested:
            if requested != ['all']:
                raise DuoError('--reply-to all cannot be mixed with other reply keys')
            replies = [t['key'] for t in work]
        else:
            if len(set(requested)) != len(requested) or any(key not in eligible for key in requested):
                raise DuoError('--reply-to must name distinct unresolved, received peer turns')
            replies = requested
        if data and not data.endswith(b'\n'):
            raise DuoError('dialogue lacks its final newline; explicit migration is required to preserve turn hashes')
        number = max((t['number'] for t in turns), default=0) + 1
        stamp = utc_now()
        if settings['style'] == 'markdown':
            separator = settings.get('write_separator')
            if separator is None:
                used = {t['_separator'] for t in turns}
                if len(used) > 1:
                    raise DuoError('mixed legacy headers require settings write_separator')
                separator = next(iter(used), ' - ')
            header = f'## {args.person}{separator}{stamp}{separator}Turn {number}{separator}{subject}'
        else:
            header = f'=== TURN {number} | {args.person} | {stamp} ==='
        metadata = '<!-- duo replies: ' + ','.join(replies) + ' -->'
        addition = ('\n\n' + header + '\n\n' + body + '\n\n' + metadata + '\n\n' + person['marker'] + '\n').encode('utf-8')
        # Parse before writing: a bad argument can never publish ambiguous bytes.
        proposed = parse_turns(data + addition, settings)
        pending_turns(proposed, settings)
        if len(proposed) != len(turns) + 1 or not proposed[-1]['complete']:
            raise DuoError('new turn does not parse as exactly one completed turn')
        if refresh_wake(state, path, settings, args.person):
            save_registration(path, state, data)
        try:
            with path.open('ab') as handle:
                handle.write(addition)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise DuoError(f'append interrupted: {exc}; inspect the tail before retrying', 5) from exc
        peer = next(p['name'] for p in settings['participants'] if p['name'] != args.person)
        command = None if args.no_wake else state.get('wake', {}).get(peer)
        turn = public_turn(proposed[-1])
    # A receiver can immediately call next, which needs the same lock.
    try:
        wake = run_wake(command, path, args.person, number)
    except OSError as exc:
        raise DuoError(f'wake reporting interrupted: {exc}; turn is committed, inspect status', 5) from exc
    return {'turn': turn, 'wake': wake}, 0


def read_command(args, path):
    deadline = time.monotonic() + args.timeout if args.command == 'wait' else None
    while True:
        try:
            data, settings, turns, state, received, pending = snapshot(path, args.settings)
        except (DuoError, UnicodeDecodeError) as exc:
            # Readers do not lock writers. A snapshot can end in a partial
            # header or UTF-8 character while an append is still in progress.
            partial = ((isinstance(exc, DuoError) and exc.code == 4)
                       or (isinstance(exc, UnicodeDecodeError)
                           and exc.reason == 'unexpected end of data'
                           and exc.end == len(exc.object)))
            if args.command != 'wait' or not partial:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {'turns': []}, 2
            time.sleep(min(args.interval, remaining))
            continue
        if args.command == 'status':
            complete = [t for t in turns if t['complete']]
            return {'turns': len(turns), 'max_number': max((t['number'] for t in turns), default=0),
                    'last': public_turn(turns[-1]) if turns else None,
                    'last_complete': public_turn(complete[-1]) if complete else None,
                    'incomplete_tail': bool(turns and not turns[-1]['complete']),
                    'pending': {name: [t['key'] for t in values] for name, values in pending.items()},
                    'receipts': state['receipts'], 'wake': state.get('wake', {})}, 0
        if args.command == 'tail':
            selected = turns[-args.turns:] if args.turns else []
            return {'turns': [public_turn(t, True) for t in selected]}, 0
        require_person(args.person, settings)
        work = [public_turn(t) for t in pending[args.person] if (args.person, t['key']) not in received]
        if work:
            return {'turns': work}, 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {'turns': []}, 2
        time.sleep(min(args.interval, remaining))


def arguments(argv):
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('init', 'append', 'next', 'wait', 'tail', 'status', 'wake'):
        command = commands.add_parser(name)
        command.add_argument('--file', required=True)
        command.add_argument('--settings')
        command.add_argument('--json', action='store_true')
        if name == 'init':
            command.add_argument('--names', required=True)
            command.add_argument('--markers')
        if name in ('append', 'next', 'wait', 'wake'):
            command.add_argument('--as', dest='person', required=True)
        if name == 'append':
            command.add_argument('--subject', required=True)
            command.add_argument('--body', required=True)
            command.add_argument('--reply-to', action='append')
            command.add_argument('--no-wake', action='store_true')
        if name == 'wake':
            action = command.add_mutually_exclusive_group(required=True)
            action.add_argument('--exec', dest='wake_exec')
            action.add_argument('--clear', action='store_true')
        if name == 'tail':
            command.add_argument('--turns', type=int, default=5)
        if name == 'wait':
            command.add_argument('--timeout', type=float, required=True)
            command.add_argument('--interval', type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.command == 'tail' and args.turns < 0:
        raise DuoError('--turns must be nonnegative')
    if args.command == 'wait' and (not math.isfinite(args.timeout) or args.timeout < 0
                                   or not math.isfinite(args.interval) or args.interval <= 0):
        raise DuoError('timeout must be finite and nonnegative; interval must be finite and positive')
    return args


def main(argv=None):
    try:
        args = arguments(argv)
        path = Path(args.file).expanduser().resolve()
        if args.command == 'init':
            result, code = init_dialogue(args, path)
        elif args.command == 'next':
            result, code = deliver(args, path)
        elif args.command == 'append':
            result, code = append_turn(args, path)
        elif args.command == 'wake':
            result, code = register_wake(args, path)
        else:
            result, code = read_command(args, path)
        if args.json:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        elif args.command in ('next', 'tail'):
            for turn in result['turns']:
                print(f"[{turn['key']}]" + (' [redelivered]' if turn.get('redelivered') else ''))
                print(turn['text'], end='\n', flush=True)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return code
    except BrokenPipeError:
        # Receipts may already be committed. They remain unresolved and next
        # safely redelivers; suppress the interpreter's second flush on exit.
        fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(fd, sys.stdout.fileno())
        os.close(fd)
        return 5
    except (DuoError, OSError, ValueError, UnicodeError) as exc:
        print(f'duo: {exc}', file=sys.stderr)
        if isinstance(exc, DuoError):
            return exc.code
        return 5 if isinstance(exc, OSError) and 'result' in locals() else 1


if __name__ == '__main__':
    sys.exit(main())
