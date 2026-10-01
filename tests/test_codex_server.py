import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from codex_server import AppServerClient, CodexServerProvider
from lab import make_provider, run

CONFIG={'timeout_seconds':3,'fast':{'model':'test-fast','reasoning_effort':'low','service_tier':'fast'},
        'strong':{'model':'test-strong','reasoning_effort':'high','service_tier':'standard'}}

class ServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        root=Path(self.folder.name)
        (root/'auth.json').write_text('test credential placeholder')
        shutil.copyfile(Path(__file__).parent/'fixtures/codex_stub.py',root/'codex')
        (root/'codex').chmod(0o755)
        self.env=patch.dict(os.environ,{'PATH':str(root)+os.pathsep+os.environ['PATH'],'CODEX_HOME':str(root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    async def test_server_reuse_fresh_threads_and_streaming(self):
        client=AppServerClient(CONFIG)
        try:
            deltas=[]
            first=await client.generate(CONFIG['fast'],'draft','17*19',None,None,deltas.append)
            pid=client.process.pid
            folder=client.folder.name
            second=await client.generate(CONFIG['fast'],'draft','17*19 again',None,None,None)
            self.assertEqual(client.process.pid,pid)
            self.assertEqual(second['server_start_ms'],0)
            self.assertEqual(first['text'],'323')
            self.assertEqual(deltas,['323'])
            self.assertIsNotNone(first['first_token_ms'])
            self.assertEqual(first['usage']['input_tokens'],100)
            self.assertEqual(first['session_service_tier'],'priority')
            self.assertEqual(client.notifications,{})
        finally:
            await client.close()
        self.assertFalse(Path(folder).exists())

    async def test_cancel_interrupts_turn_and_next_call_works(self):
        client=AppServerClient(CONFIG)
        ready=asyncio.Event()
        try:
            task=asyncio.create_task(client.generate(CONFIG['fast'],'draft','SLOW',None,None,lambda delta:ready.set()))
            await asyncio.wait_for(ready.wait(),3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            result=await client.generate(CONFIG['fast'],'draft','17*19',None,None,None)
            self.assertEqual(result['text'],'323')
        finally:await client.close()

    async def test_host_provider_reuses_process_across_runs_and_closes(self):
        provider=CodexServerProvider(CONFIG)
        try:
            a=await run(provider,'fast',{'id':'a','question':'17*19'})
            b=await run(provider,'fast',{'id':'b','question':'17*19 again'})
            self.assertEqual(a['answer'],b['answer'])
            self.assertEqual(b['calls'][0]['server_start_ms'],0)
            self.assertEqual(a['events'][0]['event'],'draft_delta')
            self.assertIsNotNone(a['first_token_ms'])
        finally:await asyncio.to_thread(provider.close)
        self.assertFalse(provider.thread.is_alive())

    async def test_disconnection_fails_active_turn(self):
        client=AppServerClient(CONFIG)
        ready=asyncio.Event()
        try:
            task=asyncio.create_task(client.generate(CONFIG['fast'],'draft','SLOW',None,None,lambda delta:ready.set()))
            await asyncio.wait_for(ready.wait(),3)
            client.process.kill()
            await client.process.wait()
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(task,3)
        finally:await client.close()

    async def test_cross_loop_cancel_waits_for_interrupt_and_allows_reuse(self):
        provider=CodexServerProvider(CONFIG)
        ready=asyncio.Event()
        try:
            task=asyncio.create_task(provider.generate('fast','draft','SLOW',on_delta=lambda delta:ready.set()))
            await asyncio.wait_for(ready.wait(),3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            result=await provider.generate('fast','draft','17*19')
            self.assertEqual(result['text'],'323')
            self.assertEqual(result['server_start_ms'],0)
        finally:await asyncio.to_thread(provider.close)

    async def test_default_factory_and_exec_fallback(self):
        provider=make_provider('codex',CONFIG)
        self.assertIsInstance(provider,CodexServerProvider)
        provider.close()
        from lab import CodexProvider
        self.assertIsInstance(make_provider('codex',dict(CONFIG,transport='exec')),CodexProvider)
