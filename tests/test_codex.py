import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lab import CodexProvider, run

CONFIG = {'timeout_seconds': 1, 'fast': {'model': 'test-fast', 'reasoning_effort': 'low'},
          'strong': {'model': 'test-strong', 'reasoning_effort': 'high', 'service_tier': 'standard'}}

def stream(answer='323'):
    return '\n'.join(json.dumps(e) for e in [
        {'type': 'thread.started', 'thread_id': 'test'},
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10}}])


class ParseTests(unittest.TestCase):
    def test_answer_and_normalized_usage(self):
        answer, usage, raw = CodexProvider.parse_events(stream())
        self.assertEqual(answer, '323')
        self.assertEqual(usage['input_tokens_details']['cached_tokens'], 20)
        self.assertEqual(raw['output_tokens'], 10)

    def test_failure_and_incomplete_are_rejected(self):
        for text in ['{"type":"turn.failed"}', '{"type":"error"}', '{"type":"thread.started"}', 'invalid']:
            with self.assertRaises((ValueError, RuntimeError)):
                CodexProvider.parse_events(text)

    def test_tool_use_is_rejected(self):
        text = stream() + '\n' + json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution'}})
        with self.assertRaises(RuntimeError):
            CodexProvider.parse_events(text)


class InvocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_isolation_auth_schema_and_no_gold_leak(self):
        captured = {}
        answer = json.dumps({'status': 'corrected', 'answer': '323', 'reason': 'Product is 323'})
        class Process:
            returncode = 0
            async def communicate(self, prompt=None):
                captured['prompt'] = prompt.decode()
                return stream(answer).encode(), b''
        async def spawn(*command, **kwargs):
            captured.update(command=command, kwargs=kwargs)
            schema_path = command[command.index('--output-schema') + 1]
            self.assertTrue(Path(schema_path).exists())
            self.assertEqual(json.loads(Path(schema_path).read_text())['required'], ['status', 'answer', 'reason'])
            return Process()
        with patch('lab.shutil.which', return_value='/fake/codex'), \
             patch('lab.asyncio.create_subprocess_exec', side_effect=spawn), \
             patch.dict('lab.os.environ', {'OPENAI_API_KEY': 'do-not-forward', 'CODEX_API_KEY': 'do-not-forward'}):
            result = await CodexProvider(CONFIG).generate('strong', 'review', '17*19', draft='313',
                      case={'expected': 'SECRET_GOLD', 'mock_strong': 'SECRET_FIXTURE'})
        self.assertNotIn('SECRET', captured['prompt'])
        self.assertNotIn('OPENAI_API_KEY', captured['kwargs']['env'])
        self.assertNotIn('CODEX_API_KEY', captured['kwargs']['env'])
        self.assertIn('--ignore-user-config', captured['command'])
        self.assertIn('forced_login_method="chatgpt"', captured['command'])
        self.assertIn('read-only', captured['command'])
        self.assertIn('service_tier="default"', captured['command'])
        self.assertEqual(result['requested_service_tier'], 'standard')
        self.assertIsNone(result['service_tier'])
        self.assertFalse(Path(captured['kwargs']['cwd']).exists())
        self.assertIsNone(result['model'])
        self.assertIsNone(result['cost_usd'])
        self.assertEqual(result['requested_model'], 'test-strong')

    async def test_fast_tier_is_priority_request(self):
        captured = []
        class Process:
            returncode = 0
            async def communicate(self, prompt=None):
                return stream().encode(), b''
        async def spawn(*command, **kwargs):
            captured.extend(command)
            return Process()
        config = dict(CONFIG, fast=dict(CONFIG['fast'], service_tier='fast', label='fast-light'))
        with patch('lab.shutil.which', return_value='/fake/codex'), \
             patch('lab.asyncio.create_subprocess_exec', side_effect=spawn):
            result = await CodexProvider(config).generate('fast', 'draft', 'Q')
        self.assertIn('service_tier="priority"', captured)
        self.assertEqual(result['model_label'], 'fast-light')
        self.assertEqual(result['requested_service_tier'], 'fast')

    async def test_timeout_kills_and_reaps_process(self):
        class Process:
            returncode = None
            killed = False
            async def communicate(self, prompt=None):
                if prompt:
                    await asyncio.sleep(10)
                return b'', b''
            def kill(self):
                self.killed = True
                self.returncode = -9
        process = Process()
        async def stop(target):
            self.assertIs(target, process)
            target.kill()
        config = dict(CONFIG, timeout_seconds=.01)
        with patch('lab.shutil.which', return_value='/fake/codex'), \
             patch('lab.asyncio.create_subprocess_exec', return_value=process), \
             patch('lab.stop_process_tree', side_effect=stop) as cleanup:
            with self.assertRaises(TimeoutError):
                await CodexProvider(config).generate('fast', 'draft', 'Q')
        self.assertTrue(process.killed)
        cleanup.assert_awaited_once_with(process)
