import argparse
import curses
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tui import ROOT, Session, Worker, width, wrap
from lab import MockProvider


def args(folder, provider='mock'):
    return argparse.Namespace(provider=provider, mode='parallel', config=None,
        cases=ROOT / 'data/cases.jsonl', output=folder)


def await_result(session):
    deadline = time.monotonic() + 3
    while session.running and time.monotonic() < deadline:
        session.poll()
        time.sleep(.01)
    assert not session.running


class SessionTests(unittest.TestCase):
    def test_mock_completion_persistence_and_custom_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Session(args(folder))
            session.key('\n')
            await_result(session)
            record = json.loads(Path(session.saved).read_text())
            self.assertEqual(record['result']['answer'], '323')
            self.assertEqual(record['result']['status'], 'corrected')
            session.key('e')
            session.key('\x15')
            for c in '새 질문':
                session.key(c)
            session.key('\n')
            self.assertEqual(session.case['question'], '새 질문')
            session.key('\n')
            self.assertFalse(session.running)
            self.assertIn('mock은 고정 사례만', session.message)
            session.key('r')
            self.assertEqual(session.case['id'], 'multiply')

    def test_direct_prompt_on_start_and_enter_runs_it(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Session(args(folder, 'codex'))
            self.assertTrue(session.editing)
            session.key('\n')
            self.assertTrue(session.editing)
            for c in '내가 입력한 질문':
                session.key(c)
            with patch.object(session, 'start') as start:
                session.key('\n')
                start.assert_called_once()
            self.assertFalse(session.editing)
            self.assertEqual(session.case, {'id': 'custom', 'question': '내가 입력한 질문'})
            session.key('n')
            self.assertTrue(session.editing)
            self.assertEqual(session.buffer, '')
            session.key('\x1b')
            self.assertFalse(session.editing)

    def test_cancel_preserves_visible_draft_without_final(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Session(args(folder))
            session.start()
            deadline = time.monotonic() + 1
            while not session.events and time.monotonic() < deadline:
                session.poll()
                time.sleep(.005)
            session.key('x')
            await_result(session)
            self.assertEqual(session.result['status'], 'cancelled')
            self.assertTrue(any(e['event'] == 'draft' for e in session.events))
            self.assertIsNone(session.result['answer'])
            self.assertFalse(any(e['event'] == 'final' for e in session.events))

    def test_display_width_and_control_filtering(self):
        self.assertEqual(width('한글abc'), 7)
        self.assertEqual(wrap('한글abc', 4), ['한글', 'abc'])
        self.assertNotIn('\x1b', ''.join(wrap('\x1b[31mhello', 40)))
        self.assertEqual(width('a\u0301'), 1)

    def test_accepted_answer_appears_once_in_ui(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Session(args(folder))
            session.events = [{'event': 'draft', 'answer': 'unique-answer', 'status': 'verifying'},
                              {'event': 'verified', 'status': 'accepted'}]
            content = '\n'.join(text for text, _ in session.content(80))
            self.assertEqual(content.count('unique-answer'), 1)
            self.assertIn('수정 없음', content)

    def test_choice_keys_and_scrolling_during_run(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Session(args(folder))
            session.key('p')
            self.assertEqual(session.provider, 'openai')
            session.key('m')
            self.assertEqual(session.mode, 'fast')
            session.key(curses.KEY_DOWN)
            self.assertEqual(session.case['id'], 'discount')
            session.running = True
            session.key(curses.KEY_NPAGE)
            self.assertEqual(session.scroll, 10)
            session.key('p')
            self.assertEqual(session.provider, 'openai')


@unittest.skipIf(os.name == 'nt', 'POSIX terminal required')
class TerminalTests(unittest.TestCase):
    def test_real_curses_terminal_runs_and_exits(self):
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 100, 0, 0))
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.Popen([sys.executable, str(ROOT/'tui.py'), '--provider', 'mock', '--output', folder],
                stdin=slave, stdout=slave, stderr=slave, env=dict(os.environ, TERM='xterm-256color'))
            os.close(slave)
            output = b''
            started = False
            quitting = False
            deadline = time.monotonic() + 8
            try:
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .1)[0]:
                        try:
                            output += os.read(master, 65536)
                        except OSError:
                            break
                    if not started and b'FAST VERIFY LAB' in output:
                        os.write(master, b'\n')
                        started = True
                    if not quitting and list(Path(folder).glob('ui-*.json')):
                        os.write(master, b'q')
                        quitting = True
                    if process.poll() is not None:
                        break
                process.wait(timeout=3)
                self.assertEqual(process.returncode, 0, output.decode(errors='replace'))
                saved = list(Path(folder).glob('ui-*.json'))
                self.assertEqual(len(saved), 1)
                self.assertEqual(json.loads(saved[0].read_text())['result']['answer'], '323')
                self.assertIn(b'DRAFT', output)
                self.assertIn(b'REVIEW', output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)
