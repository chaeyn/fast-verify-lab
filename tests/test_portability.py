"""Cross-platform transport selection and subprocess lifecycle checks."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from codex_server import preferred_transport
from lab import CodexProvider, ProviderError, make_provider
from process_utils import process_options, stop_process_tree
from providers import ClaudeProvider, HTTPProvider, load_config


class TransportTests(unittest.TestCase):
    def test_windows_uses_exec_without_reading_credentials(self):
        with patch('codex_server.os.name', 'nt'), \
                patch.object(Path, 'is_file', side_effect=AssertionError('Unexpected credential lookup')):
            self.assertEqual(preferred_transport({'transport': 'app-server'}), 'exec')

    def test_factory_uses_exec_on_windows(self):
        with patch('codex_server.os.name', 'nt'), patch('lab.shutil.which', return_value='codex'):
            provider = make_provider('codex', {'fast': {'model': 'draft'}, 'strong': {'model': 'review'}})
        self.assertIsInstance(provider, CodexProvider)

    def test_missing_file_login_uses_native_cli_auth(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, CODEX_HOME=folder):
            self.assertEqual(preferred_transport({}), 'exec')

    @unittest.skipIf(os.name == 'nt', 'Windows always uses the native exec transport')
    def test_file_login_uses_app_server_without_reading_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, CODEX_HOME=folder):
            (Path(folder) / 'auth.json').write_text('test-only', encoding='utf-8')
            with patch.object(Path, 'read_text', side_effect=AssertionError('Unexpected credential read')):
                self.assertEqual(preferred_transport({}), 'app-server')
                self.assertEqual(preferred_transport({'transport': 'exec'}), 'exec')

    def test_invalid_transport_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'app-server or exec'):
            preferred_transport({'transport': 'typo'})

    def test_windows_process_group_options(self):
        with patch('process_utils.os.name', 'nt'), \
                patch('process_utils.subprocess.CREATE_NEW_PROCESS_GROUP', 0x200, create=True):
            self.assertEqual(process_options(), {'creationflags': 0x200})

    def test_config_secret_in_list_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'config.json'
            target.write_text('{"unused": [{"access_token": "secret"}]}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'environment variables'):
                load_config('configured', target)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_closes_descendant_output_pipe_and_reaps_parent(self):
        # The child inherits stdout. Killing only the parent leaves read() blocked.
        code = ('import subprocess,sys,time; '
                'subprocess.Popen([sys.executable,"-c",'
                '"import time; print(\'ready\',flush=True); time.sleep(60)"]); '
                'time.sleep(60)')
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', code,
            stdout=asyncio.subprocess.PIPE, **process_options())
        try:
            self.assertEqual((await asyncio.wait_for(process.stdout.readline(), 5)).strip(), b'ready')
            await asyncio.wait_for(stop_process_tree(process), 5)
            self.assertEqual(await asyncio.wait_for(process.stdout.read(), 2), b'')
            self.assertIsNotNone(process.returncode)
            await stop_process_tree(process)  # Closing twice is safe.
        finally:
            if process.returncode is None:
                await stop_process_tree(process)

    @unittest.skipIf(os.name == 'nt', 'POSIX process groups survive the leader')
    async def test_stop_reaps_descendant_after_parent_has_exited(self):
        code = ('import subprocess,sys; '
                'subprocess.Popen([sys.executable,"-c",'
                '"import time; print(\'ready\',flush=True); time.sleep(60)"])')
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', code,
            stdout=asyncio.subprocess.PIPE, **process_options())
        try:
            await asyncio.wait_for(process.stdout.readline(), 5)
            async with asyncio.timeout(3):
                while process.returncode is None:
                    await asyncio.sleep(.01)
            await asyncio.wait_for(stop_process_tree(process), 5)
            self.assertEqual(await asyncio.wait_for(process.stdout.read(), 2), b'')
        finally:
            await stop_process_tree(process)

    async def test_windows_stop_uses_taskkill_tree_and_reaps_parent(self):
        class Process:
            pid = 4123
            returncode = None
            def kill(self):
                self.returncode = 1
            async def wait(self):
                return self.returncode
        killer = AsyncMock()
        killer.wait.return_value = 0
        process = Process()
        with patch('process_utils.os.name', 'nt'), \
                patch('process_utils.asyncio.create_subprocess_exec', return_value=killer) as spawn:
            await stop_process_tree(process)
        self.assertEqual(spawn.call_args.args, ('taskkill', '/PID', '4123', '/T', '/F'))
        self.assertEqual(process.returncode, 1)

    async def test_windows_taskkill_error_still_reaps_direct_child(self):
        process = AsyncMock()
        process.pid, process.returncode = 4123, None
        from unittest.mock import Mock
        process.kill = Mock()
        with patch('process_utils.os.name', 'nt'), \
                patch('process_utils.asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
            await stop_process_tree(process)
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_claude_cancel_cleans_process_and_temporary_folder(self):
        ready = asyncio.Event()
        class Process:
            returncode = None
            async def communicate(self, prompt=None):
                if prompt is not None:
                    ready.set()
                    await asyncio.Event().wait()
                return b'', b''
        process = Process()
        with patch('providers.shutil.which', return_value='claude'), \
                patch('providers.asyncio.create_subprocess_exec', return_value=process) as spawn, \
                patch('providers.stop_process_tree', new_callable=AsyncMock) as stop:
            provider = ClaudeProvider({'fast': {'model': 'haiku'}, 'strong': {'model': 'sonnet'}})
            task = asyncio.create_task(provider.generate('fast', 'draft', 'question'))
            await asyncio.wait_for(ready.wait(), 2)
            folder = spawn.call_args.kwargs['cwd']
            self.assertTrue(Path(folder).exists())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            stop.assert_awaited_once_with(process)
            self.assertFalse(Path(folder).exists())
            self.assertIn('--no-session-persistence', spawn.call_args.args)
            options = spawn.call_args.kwargs
            self.assertNotIn('ANTHROPIC_API_KEY', options['env'])

    async def test_claude_invalid_json_and_exit_errors_are_redacted(self):
        config = {'fast': {'model': 'haiku'}, 'strong': {'model': 'sonnet'}}
        for returncode, expected in ((0, 'Claude Code returned invalid JSON'),
                                     (1, 'Claude Code exited with code 1')):
            process = AsyncMock()
            process.returncode = returncode
            process.communicate.return_value = (b'private credential', b'private stderr')
            with patch('providers.shutil.which', return_value='claude'), \
                    patch('providers.asyncio.create_subprocess_exec', return_value=process):
                with self.assertRaisesRegex(ProviderError, '^' + expected + '$'):
                    await ClaudeProvider(config).generate('fast', 'draft', 'question')

    async def test_claude_non_string_answer_is_rejected(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (json.dumps({'subtype': 'success', 'result': {}}).encode(), b'')
        with patch('providers.shutil.which', return_value='claude'), \
                patch('providers.asyncio.create_subprocess_exec', return_value=process):
            with self.assertRaisesRegex(ProviderError, 'did not complete'):
                await ClaudeProvider({'fast': {'model': 'haiku'}, 'strong': {'model': 'sonnet'}}).generate(
                    'fast', 'draft', 'question')

    async def test_api_invalid_json_does_not_expose_response(self):
        with patch.dict(os.environ, LAB_TEST_KEY='placeholder'), \
                patch('providers.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = b'private response'
            provider = HTTPProvider({'api_key_env': 'LAB_TEST_KEY', 'fast': {'model': 'test'},
                                     'strong': {'model': 'test'}}, 'api')
            with self.assertRaisesRegex(ProviderError, '^API returned invalid JSON$'):
                await provider.generate('fast', 'draft', 'question')
