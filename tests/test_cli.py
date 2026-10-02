"""Exercise prompt input, streamed output, user paths, and source entrypoints."""
import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cli
import paths
from configure import wizard

ROOT = Path(__file__).parents[1]


class UserPathsTests(unittest.TestCase):
    def test_user_paths_and_overrides_on_each_platform(self):
        with tempfile.TemporaryDirectory() as folder, patch('paths.Path.home', return_value=Path(folder)), \
                patch.dict(os.environ, {}, clear=True):
            home = Path(folder)
            with patch('paths.sys.platform', 'linux'):
                self.assertEqual(paths.user_config_dir(), home / '.config/fast-verify-lab')
                self.assertEqual(paths.user_results_dir(), home / '.local/state/fast-verify-lab/results')
            with patch('paths.sys.platform', 'darwin'):
                self.assertEqual(paths.user_config_dir(), home / 'Library/Application Support/fast-verify-lab')
            with patch('paths.sys.platform', 'win32'):
                self.assertEqual(paths.user_config_dir(), home / 'AppData/Roaming/fast-verify-lab')
                self.assertEqual(paths.user_results_dir(), home / 'AppData/Local/fast-verify-lab/results')
            with patch.dict(os.environ, FAST_VERIFY_CONFIG=str(home/'custom.json'), FAST_VERIFY_RESULTS_DIR=str(home/'runs')):
                self.assertEqual(paths.config_path(), home/'custom.json')
                self.assertEqual(paths.user_results_dir(), home/'runs')
                self.assertEqual(paths.config_path(path=home/'explicit.json'), home/'explicit.json')
                self.assertEqual(paths.config_path('mock'), ROOT/'config.example.json')

    def test_legacy_local_config_precedes_user_default(self):
        with tempfile.TemporaryDirectory() as folder, patch('paths.Path.cwd', return_value=Path(folder)), \
                patch.dict(os.environ, {}, clear=True):
            local = Path(folder)/'config.local.json'
            local.write_text('{}', encoding='utf-8')
            self.assertEqual(paths.config_path(), local)

    def test_wizard_creates_user_directory_and_preserves_default_tiers(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'nested/config.json'
            answers = iter(['1', '', '', '1', '', ''])
            with redirect_stdout(io.StringIO()):
                wizard(destination, read=lambda _: next(answers))
            data = json.loads(destination.read_text(encoding='utf-8'))
            self.assertEqual(data['fast']['service_tier'], 'fast')
            self.assertEqual(data['strong']['service_tier'], 'standard')


class AskTests(unittest.TestCase):
    def options(self, *args):
        return cli.parser().parse_args(['ask', '--no-save', *args])

    def test_prompt_file_stdin_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            prompt = Path(folder)/'question.txt'
            prompt.write_text('한국어 질문\n두 번째 줄', encoding='utf-8')
            self.assertEqual(cli.question_case(self.options('--prompt-file', str(prompt)))['question'], '한국어 질문\n두 번째 줄')
            with self.assertRaisesRegex(ValueError, 'one input source'):
                cli.question_case(self.options('question', '--prompt-file', str(prompt)))
        with patch('cli.sys.stdin', io.StringIO('stdin question\n')):
            self.assertEqual(cli.question_case(self.options())['question'], 'stdin question')
        with patch('cli.sys.stdin', io.StringIO(' \n')):
            with self.assertRaisesRegex(ValueError, 'empty'):
                cli.question_case(self.options())
        with self.assertRaisesRegex(ValueError, 'sample case'):
            cli.question_case(self.options('--provider', 'mock', 'custom'))

    def test_streamed_accepted_answer_prints_once_and_closes_provider(self):
        class Provider:
            supports_streaming = True
            closed = False
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'draft':
                    kwargs['on_delta']('3')
                    kwargs['on_delta']('23')
                    return {'text': '323', 'cost_usd': None}
                return {'text': json.dumps({'status':'accepted', 'answer':'323', 'reason':'checked'}), 'cost_usd': None}
            def close(self):
                self.closed = True
        provider = Provider()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('cli.load_config', return_value={}), patch.object(cli.lab, 'make_provider', return_value=provider), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            status = asyncio.run(cli.ask(self.options('question')))
        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), '323\n')
        self.assertIn('No changes needed', stderr.getvalue())
        self.assertTrue(provider.closed)

    def test_json_output_and_utf8_record_from_other_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run([sys.executable, str(ROOT/'cli.py'), 'ask', '--provider', 'mock',
                                      '--case', 'multiply', '--json', '--output', folder],
                capture_output=True, text=True, encoding='utf-8', cwd=folder, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            events = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual([e['event'] for e in events], ['draft', 'final'])
            records = list(Path(folder).glob('ask-*.json'))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text(encoding='utf-8'))
            self.assertEqual(record['result']['answer'], '323')

    def test_version_and_cli_import_do_not_require_curses(self):
        script = ('import builtins,runpy,sys\noriginal=builtins.__import__\n'
                  'def guarded(name,*args,**kw):\n'
                  ' if name=="curses": raise ImportError("curses unavailable")\n'
                  ' return original(name,*args,**kw)\n'
                  'builtins.__import__=guarded\n'
                  f'sys.path.insert(0,{str(ROOT)!r})\nsys.argv=["cli.py","--version"]\n'
                  f'runpy.run_path({str(ROOT/"cli.py")!r},run_name="__main__")\n')
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('0.1.0', result.stdout)

    def test_model_control_characters_do_not_reach_terminal(self):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.Printer()({'event':'draft','status':'unreviewed','answer':'\x1b[31mAnswer\x00'})
        self.assertNotIn('\x1b', output.getvalue())
        self.assertNotIn('\x00', output.getvalue())
