import asyncio
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lab import MockProvider, OpenAIProvider, estimated_cost, grade, parse_review, run, summary

CASES = [json.loads(line) for line in (Path(__file__).parents[1] / 'data/cases.jsonl').read_text().splitlines()]


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_modes_and_call_counts(self):
        for mode, count in [('fast', 1), ('strong', 1), ('sequential', 2), ('parallel', 3)]:
            row = await run(MockProvider(), mode, CASES[0])
            self.assertEqual(len(row['calls']), count)
            self.assertEqual(row['answer'], '313' if mode == 'fast' else '323')
            self.assertIsNone(row['cost_usd'])

    async def test_accepted_draft_is_not_emitted_again(self):
        row = await run(MockProvider(), 'sequential', CASES[1])
        self.assertEqual([e['event'] for e in row['events']], ['draft', 'verified'])
        self.assertNotIn('answer', row['events'][-1])
        self.assertEqual(row['answer'], row['draft'])
        self.assertEqual(row['status'], 'accepted')
        self.assertEqual([c['stage'] for c in row['calls']], ['draft', 'review'])

    async def test_fast_only_emits_answer_once(self):
        row = await run(MockProvider(), 'fast', CASES[0])
        self.assertEqual([e['event'] for e in row['events']], ['draft'])

    async def test_parallel_starts_before_draft_and_publishes_without_waiting(self):
        started, release = asyncio.Event(), asyncio.Event()
        class Provider:
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'independent':
                    started.set()
                    await release.wait()
                elif stage == 'draft':
                    await asyncio.wait_for(started.wait(), 1)
                answer = '313' if role == 'fast' else '323'
                if stage == 'review':
                    answer = json.dumps({'status': 'corrected', 'answer': '323', 'reason': 'Arithmetic'})
                return {'text': answer, 'cost_usd': None}
        def emit(event):
            if event['event'] == 'draft':
                self.assertFalse(release.is_set())
                release.set()
        row = await asyncio.wait_for(run(Provider(), 'parallel', CASES[0], emit), 2)
        self.assertEqual([e['event'] for e in row['events']], ['draft', 'final'])
        self.assertEqual(row['answer'], '323')

    async def test_verifier_failure_preserves_unverified_draft(self):
        class Provider(MockProvider):
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'review':
                    raise TimeoutError()
                return await super().generate(role, stage, question, **kwargs)
        row = await run(Provider(), 'sequential', CASES[0])
        self.assertEqual(row['answer'], '313')
        self.assertEqual(row['status'], 'verification_failed')
        self.assertEqual(len(row['calls']), 2)
        self.assertIsNone(row['cost_usd'])

    async def test_invalid_review_is_failure(self):
        class Provider(MockProvider):
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'review':
                    return {'text': 'not json', 'cost_usd': None}
                return await super().generate(role, stage, question, **kwargs)
        self.assertEqual((await run(Provider(), 'parallel', CASES[0]))['status'], 'verification_failed')

    async def test_independent_failure_is_observed(self):
        class Provider(MockProvider):
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'independent':
                    raise RuntimeError()
                return await super().generate(role, stage, question, **kwargs)
        row = await run(Provider(), 'parallel', CASES[0])
        self.assertEqual(row['status'], 'verification_failed')
        self.assertEqual(row['draft'], '313')

    async def test_failed_draft_has_no_answer_latency(self):
        class Provider:
            async def generate(self, *args, **kwargs):
                raise RuntimeError()
        row = await run(Provider(), 'parallel', CASES[0])
        self.assertEqual(row['status'], 'failed')
        self.assertIsNone(row['first_answer_ms'])

    async def test_uncertain_is_not_accepted(self):
        class Provider(MockProvider):
            async def generate(self, role, stage, question, **kwargs):
                if stage == 'review':
                    return {'text': json.dumps({'status': 'uncertain', 'answer': 'unknown', 'reason': 'No evidence'}), 'cost_usd': None}
                return await super().generate(role, stage, question, **kwargs)
        self.assertEqual((await run(Provider(), 'sequential', CASES[0]))['status'], 'uncertain')

    async def test_correct_draft_can_be_broken_by_verifier(self):
        row = await run(MockProvider(), 'parallel', CASES[-1])
        row['grade'] = grade(row, CASES[-1]['expected'])
        self.assertTrue(row['grade']['regression'])
        self.assertEqual(summary([row])['parallel']['regressions'], 1)


class ValidationTests(unittest.TestCase):
    def test_review_consistency(self):
        for status, answer in [('accepted', 'wrong'), ('corrected', 'draft')]:
            with self.assertRaises(ValueError):
                parse_review(json.dumps({'status': status, 'answer': answer, 'reason': ''}), 'draft')

    def test_cached_token_cost_and_unknown_price(self):
        usage = {'input_tokens': 1000, 'input_tokens_details': {'cached_tokens': 200}, 'output_tokens': 500}
        spec = {'input_usd_per_million': 2, 'cached_input_usd_per_million': 1, 'output_usd_per_million': 8}
        self.assertAlmostEqual(estimated_cost(usage, spec), .0058)
        self.assertIsNone(estimated_cost(usage, {}))
        self.assertIsNone(estimated_cost(None, spec))


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_adapter_contract_with_local_server(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'completed', 'model': 'test-model', 'id': 'test-response',
                    'service_tier': 'default', 'usage': {'input_tokens': 10, 'output_tokens': 2},
                    'output': [{'type': 'reasoning'}, {'type': 'message', 'content': [
                        {'type': 'output_text', 'text': '323'}]}]}).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = {'base_url': f'http://127.0.0.1:{server.server_port}', 'timeout_seconds': 2,
                  'max_output_tokens': 4096, 'fast': {'model': 'test-model'},
                  'strong': {'model': 'test-model', 'reasoning_effort': 'high'}}
        try:
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'local-test-key'}):
                result = await OpenAIProvider(config).generate('strong', 'review', 'Question', draft='313')
            self.assertEqual(result['text'], '323')
            self.assertEqual(received[0][0], '/responses')
            payload = received[0][1]
            self.assertFalse(payload['store'])
            self.assertEqual(payload['reasoning'], {'effort': 'high'})
            self.assertEqual(payload['text']['format']['type'], 'json_object')
            self.assertNotIn('expected', payload['input'])
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join()

    async def test_incomplete_response_is_not_a_final_answer(self):
        config = {'base_url': 'https://api.openai.com/v1', 'max_output_tokens': 10,
                  'fast': {'model': 'test'}, 'strong': {'model': 'test'}}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}):
            provider = OpenAIProvider(config)
        with patch.object(provider, '_request', return_value={'status': 'incomplete', 'output': []}):
            with self.assertRaises(RuntimeError):
                await provider.generate('fast', 'draft', 'Question')
