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

@unittest.skipIf(os.name == 'nt', 'POSIX App Server transport; Windows uses Codex exec')
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

    async def test_crashed_server_restart_removes_old_working_directory(self):
        client=AppServerClient(CONFIG)
        try:
            await client.start()
            old_folder=client.folder.name
            client.process.kill()
            await client.process.wait()
            result=await client.generate(CONFIG['fast'],'draft','17*19',None,None,None)
            self.assertEqual(result['text'],'323')
            self.assertFalse(Path(old_folder).exists())
            self.assertNotEqual(client.folder.name,old_folder)
        finally:await client.close()

    async def test_cancel_before_turn_id_stops_untracked_generation(self):
        client=AppServerClient(CONFIG)
        request=client.request
        ready=asyncio.Event()
        async def delayed_response(method,params):
            response=await request(method,params)
            if method=='turn/start':
                ready.set()
                await asyncio.Event().wait()
            return response
        try:
            with patch.object(client,'request',side_effect=delayed_response):
                task=asyncio.create_task(client.generate(CONFIG['fast'],'draft','SLOW',None,None,None))
                await asyncio.wait_for(ready.wait(),3)
                process=client.process
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            self.assertIsNotNone(process.returncode)
            self.assertIsNone(client.process)
            self.assertEqual(client.notifications,{})
            result=await client.generate(CONFIG['fast'],'draft','17*19',None,None,None)
            self.assertEqual(result['text'],'323')
        finally:await client.close()

    async def test_denied_credential_link_cleans_directory_without_reading_secret(self):
        client=AppServerClient(CONFIG)
        folders=[]
        temporary_directory=tempfile.TemporaryDirectory
        def record_folder(**kwargs):
            folder=temporary_directory(**kwargs)
            folders.append(folder.name)
            return folder
        with patch('codex_server.tempfile.TemporaryDirectory',side_effect=record_folder), \
                patch.object(Path,'symlink_to',side_effect=PermissionError), \
                patch.object(Path,'read_text',side_effect=AssertionError('Credential contents must not be read')):
            with self.assertRaisesRegex(ValueError,'transport to exec'):
                await client.start()
        self.assertEqual(len(folders),1)
        self.assertFalse(Path(folders[0]).exists())
        self.assertIsNone(client.folder)
        self.assertIsNone(client.process)

    async def test_subprocess_start_failure_cleans_directory(self):
        client=AppServerClient(CONFIG)
        with patch('codex_server.asyncio.create_subprocess_exec',side_effect=OSError('start failed')):
            with self.assertRaises(OSError):await client.start()
        self.assertIsNone(client.folder)
        self.assertIsNone(client.process)

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
