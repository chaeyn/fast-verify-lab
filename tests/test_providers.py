import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lab import make_provider, run
from providers import HTTPProvider, RoleProvider, ClaudeProvider, load_config
from configure import wizard, doctor


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_contract_for_both_protocols_and_failure(self):
        records = []
        class Handler(BaseHTTPRequestHandler):
            failure = False
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                records.append((self.path, {k.lower():v for k,v in self.headers.items()}, body))
                if self.failure:
                    self.send_response(401); self.end_headers(); self.wfile.write(b'secret-token-private-question'); return
                if self.path == '/v1/messages':
                    data = {'stop_reason': 'end_turn', 'model': 'test-claude', 'content': [{'type':'text','text':'323'}],
                            'usage': {'input_tokens': 7, 'output_tokens': 2, 'cache_read_input_tokens': 3}}
                else:
                    data = {'model':'test-api','choices':[{'finish_reason':'stop','message':{'content':'323'}}],
                            'usage':{'prompt_tokens':10,'completion_tokens':2}}
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(data).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        config = {'base_url':f'http://127.0.0.1:{server.server_port}/v1','api_key_env':'LAB_TEST_KEY',
                  'fast':{'model':'test-fast'}, 'strong':{'model':'test-review'}}
        try:
            with patch.dict(os.environ, LAB_TEST_KEY='fake-key'):
                for name in ('anthropic','api'):
                    provider = HTTPProvider(config, name)
                    answer = await provider.generate('fast','draft','17*19?')
                    self.assertEqual(answer['text'],'323')
                    self.assertEqual(answer['usage']['input_tokens'],10)
                self.assertEqual(records[0][0],'/v1/messages')
                self.assertEqual(records[0][1]['x-api-key'],'fake-key')
                self.assertEqual(records[0][1]['anthropic-version'],'2023-06-01')
                self.assertIn('system',records[0][2])
                self.assertEqual(records[1][0],'/v1/chat/completions')
                self.assertEqual(records[1][1]['authorization'],'Bearer fake-key')
                Handler.failure = True
                with self.assertRaisesRegex(RuntimeError, '^API HTTP 401$'):
                    await provider.generate('fast','draft','question')
        finally:
            await asyncio.to_thread(server.shutdown); server.server_close(); thread.join()

    async def test_truncation_and_tool_use_are_rejected(self):
        with patch.dict(os.environ, LAB_TEST_KEY='fake'):
            for kind, data in [('anthropic', {'stop_reason':'max_tokens','content':[{'type':'text','text':'partial'}]}),
                               ('api', {'choices':[{'finish_reason':'tool_calls','message':{'content':'partial'}}]})]:
                config={'api_key_env':'LAB_TEST_KEY','fast':{'model':'test'},'strong':{'model':'test'}}
                provider=HTTPProvider(config,kind)
                with patch.object(provider,'request',return_value=data):
                    with self.assertRaises(RuntimeError):
                        await provider.generate('fast','draft','question')

    async def test_mixed_roles_forward_streaming_and_use_distinct_clients(self):
        class Draft:
            supports_streaming = True
            async def generate(self, role, stage, question, **kw):
                self.assertion = role
                kw['on_delta']('323')
                return {'text':'323','cost_usd':None}
        class Reviewer:
            async def generate(self, role, stage, question, **kw):
                if 'on_delta' in kw:
                    raise AssertionError('Unexpected stream option')
                return {'text':json.dumps({'status':'accepted','answer':kw['draft'],'reason':'checked'}),'cost_usd':None}
        config={'fast':{'provider':'codex','model':'draft'},'strong':{'provider':'claude','model':'review'}}
        routed=RoleProvider(config)
        with patch('lab.make_provider', side_effect=[Draft(),Reviewer()]) as factory:
            routed.prepare('sequential')
            result=await run(routed,'sequential',{'id':'custom','question':'17*19?'})
            self.assertEqual(result['status'],'accepted')
            self.assertEqual([e['event'] for e in result['events']],['draft_delta','draft','verified'])
            self.assertEqual([c['provider'] for c in result['calls']],['codex','claude'])
            self.assertEqual(factory.call_count,2)

    async def test_same_connection_reuses_client_with_distinct_models(self):
        config={'fast':{'provider':'codex','model':'fast-model'},'strong':{'provider':'codex','model':'review-model'}}
        routed=RoleProvider(config)
        with patch('lab.make_provider') as factory:
            self.assertIs(routed.client('fast'), routed.client('strong'))
            self.assertEqual(factory.call_count,1)
            self.assertEqual(factory.call_args.args[1]['fast']['model'],'fast-model')
            self.assertEqual(factory.call_args.args[1]['strong']['model'],'review-model')

    @unittest.skipIf(os.name == 'nt', 'POSIX executable fixture; process cleanup has separate portable tests')
    async def test_claude_cli_isolation_and_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            stub=Path(folder)/'claude'
            stub.write_text('#!/usr/bin/env python3\nimport json,sys,os,time\n'
                'args=sys.argv[1:]\nassert args[args.index("--tools")+1] == ""\n'
                'assert args[args.index("--setting-sources")+1] == ""\n'
                'assert "--no-session-persistence" in args\nassert "--strict-mcp-config" in args\n'
                'assert "ANTHROPIC_API_KEY" not in os.environ\n'
                'prompt=json.load(sys.stdin)\nassert "expected" not in prompt\n'
                'assert not os.listdir(os.getcwd())\n'
                'if prompt["question"] == "wait": time.sleep(10)\n'
                'print(json.dumps({"subtype":"success","is_error":False,"result":"323","usage":{"input_tokens":2,"output_tokens":1}}))\n')
            stub.chmod(0o755)
            config={'timeout_seconds':3,'fast':{'model':'haiku'},'strong':{'model':'sonnet'}}
            with patch('providers.shutil.which',return_value=str(stub)), patch.dict(os.environ,ANTHROPIC_API_KEY='should-be-stripped'):
                provider=ClaudeProvider(config)
                result=await provider.generate('fast','draft','17*19?',case={'expected':'secret-gold'})
                self.assertEqual(result['text'],'323')
                config['timeout_seconds'] = .2
                with self.assertRaises(TimeoutError):
                    await provider.generate('fast','draft','wait')


class SetupTests(unittest.TestCase):
    def test_wizard_saves_mixed_config_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json'
            answers=iter(['1','gpt-6-luna','low','4','my-claude-model','https://api.anthropic.com/v1','REVIEW_API_KEY'])
            with patch('builtins.print'):
                wizard(path,read=lambda _:next(answers))
            config=load_config('configured',path)
            self.assertEqual(config['fast']['provider'],'codex')
            self.assertEqual(config['strong']['provider'],'anthropic')
            self.assertEqual(config['strong']['api_key_env'],'REVIEW_API_KEY')

    def test_doctor_checks_claude_login_for_claude_preset(self):
        path = Path(__file__).parents[1] / 'config.claude.json'
        with patch('configure.shutil.which', return_value='/test/claude'), \
             patch('configure.subprocess.run', return_value=SimpleNamespace(returncode=1)) as command, \
             patch('builtins.print'):
            self.assertFalse(doctor(path))
            self.assertEqual(command.call_args.args[0], ['/test/claude', 'auth', 'status'])

    def test_embedded_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'; path.write_text('{"fast":{"api_key":"secret"}}')
            with self.assertRaisesRegex(ValueError,'environment variables'):
                load_config('configured',path)

    def test_unknown_provider_does_not_silently_call_codex(self):
        with self.assertRaisesRegex(ValueError,'Unknown provider'):
            make_provider('typo',{})
