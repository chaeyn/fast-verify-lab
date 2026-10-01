"""Persistent, private stdio App Server transport. No credentials are decoded here."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import errno
import tempfile
import threading
import time


class AppServerClient:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.reader = None
        self.pending, self.notifications = {}, {}
        self.sequence = 0
        self.start_lock = asyncio.Lock()
        self.folder = None

    async def start(self):
        async with self.start_lock:
            if self.process and self.process.returncode is None:
                return 0.0
            started = time.perf_counter()
            binary = shutil.which('codex')
            if not binary:
                raise ValueError('Install Codex CLI and run codex login first')
            credential_root = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
            credential = credential_root / 'auth.json'
            if not credential.is_file():
                raise ValueError('App Server needs file-based Codex login. Use transport=exec for keyring-only login.')
            self.folder = tempfile.TemporaryDirectory(prefix='fast-verify-server-')
            home = Path(self.folder.name) / 'codex-home'
            home.mkdir()
            # Link the native credential file; never read, copy, or log its contents.
            (home / 'auth.json').symlink_to(credential.resolve())
            env = os.environ.copy()
            for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN'):
                env.pop(key, None)
            env['CODEX_HOME'] = str(home)
            self.process = await asyncio.create_subprocess_exec(binary, 'app-server', '--stdio',
                '-c', 'project_doc_max_bytes=0', '-c', 'features.shell_tool=false',
                '-c', 'web_search="disabled"', '-c', 'forced_login_method="chatgpt"',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, cwd=self.folder.name, env=env, start_new_session=True)
            self.reader = asyncio.create_task(self.read())
            try:
                await self.request('initialize', {'clientInfo': {'name': 'fast_verify_lab', 'version': '0.2.0'},
                    'capabilities': {'experimentalApi': True}})
                await self.send({'method': 'initialized', 'params': {}})
                account = await self.request('account/read', {'refreshToken': False})
                if (account.get('account') or {}).get('type') != 'chatgpt':
                    raise ValueError('Log in to Codex with ChatGPT before running this experiment')
            except BaseException:
                await self.close()
                raise
            return (time.perf_counter() - started) * 1000

    async def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode())
        await self.process.stdin.drain()

    async def request(self, method, params):
        self.sequence += 1
        identifier = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        try:
            await self.send({'id': identifier, 'method': method, 'params': params})
            return await asyncio.wait_for(future, self.config['timeout_seconds'])
        finally:
            self.pending.pop(identifier, None)

    async def read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if 'id' in message and 'method' not in message:
                    future = self.pending.get(message['id'])
                    if future and not future.done():
                        if 'error' in message:
                            future.set_exception(RuntimeError('App Server rejected the request'))
                        else:
                            future.set_result(message['result'])
                elif 'id' in message:
                    # This experiment does not approve tools or accept interactive requests.
                    await self.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Interactive tools disabled'}})
                else:
                    thread_id = message.get('params', {}).get('threadId')
                    if thread_id in self.notifications:
                        self.notifications[thread_id].put_nowait(message)
        except (ValueError, OSError):
            pass
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(RuntimeError('App Server disconnected'))
            for queue in self.notifications.values():
                queue.put_nowait({'method': 'disconnected', 'params': {}})

    async def close(self):
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await self.process.wait()
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        if self.folder:
            for attempt in range(5):
                try:
                    self.folder.cleanup()
                    break
                except OSError as exc:
                    if exc.errno != errno.ENOTEMPTY or attempt == 4:
                        raise
                    await asyncio.sleep(.05)
        self.process = self.reader = self.folder = None
        self.notifications.clear()

    async def generate(self, spec, stage, question, draft, independent, on_delta):
        from lab import REVIEW, SOLVE
        started = time.perf_counter()
        startup_ms = await self.start()
        tier = {'standard': 'default', 'fast': 'priority'}.get(spec.get('service_tier'), spec.get('service_tier'))
        thread_started = time.perf_counter()
        response = await self.request('thread/start', {'model': spec['model'], 'modelProvider': 'openai',
            'serviceTier': tier, 'cwd': self.folder.name, 'approvalPolicy': 'never', 'sandbox': 'read-only',
            'ephemeral': True, 'baseInstructions': REVIEW if stage == 'review' else SOLVE,
            'developerInstructions': 'Only answer the supplied question. Never use tools, inspect files, or execute commands.'})
        thread_ms = (time.perf_counter() - thread_started) * 1000
        thread_id = response['thread']['id']
        queue = self.notifications.setdefault(thread_id, asyncio.Queue())
        turn_id = None
        first_token_ms = None
        usage, text = None, None
        params = {'threadId': thread_id, 'input': [{'type': 'text', 'text': json.dumps({
            'question': question, 'draft': draft, 'independent_answer': independent}, ensure_ascii=False)}],
            'effort': spec.get('reasoning_effort'), 'serviceTier': tier}
        if stage == 'review':
            params['outputSchema'] = {'type': 'object', 'properties': {
                'status': {'type': 'string', 'enum': ['accepted', 'corrected', 'uncertain']},
                'answer': {'type': 'string'}, 'reason': {'type': 'string'}},
                'required': ['status', 'answer', 'reason'], 'additionalProperties': False}
        try:
            turn = await self.request('turn/start', params)
            turn_id = turn['turn']['id']
            async with asyncio.timeout(self.config['timeout_seconds']):
                while True:
                    message = await queue.get()
                    method, data = message['method'], message['params']
                    if method == 'disconnected':
                        raise RuntimeError('App Server disconnected')
                    if data.get('turnId') and data['turnId'] != turn_id:
                        continue
                    if method == 'item/agentMessage/delta':
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000
                        if on_delta:
                            on_delta(data['delta'])
                    elif method == 'item/completed':
                        item = data['item']
                        if item['type'] == 'agentMessage' and item.get('phase') != 'commentary':
                            text = item['text']
                        elif item['type'] not in ('agentMessage', 'reasoning', 'userMessage'):
                            raise RuntimeError('App Server used tools; pure-model experiment rejected')
                    elif method == 'thread/tokenUsage/updated':
                        usage = data['tokenUsage']['last']
                    elif method == 'turn/completed':
                        completed = data['turn']
                        if completed['status'] != 'completed' or not text:
                            raise RuntimeError('App Server did not complete with an answer')
                        break
        except BaseException:
            if turn_id and self.process and self.process.returncode is None:
                try:
                    await asyncio.wait_for(self.request('turn/interrupt', {'threadId': thread_id, 'turnId': turn_id}), 2)
                except Exception:
                    await self.close()
            raise
        finally:
            if self.process and self.process.returncode is None:
                try:
                    await asyncio.wait_for(self.request('thread/unsubscribe', {'threadId': thread_id}), 2)
                except Exception:
                    pass
            self.notifications.pop(thread_id, None)
        normalized = None if usage is None else {'input_tokens': usage['inputTokens'],
            'output_tokens': usage['outputTokens'], 'input_tokens_details': {'cached_tokens': usage['cachedInputTokens']}}
        return {'text': text, 'model': None, 'requested_model': spec['model'], 'session_model': response['model'],
            'model_label': spec.get('label', spec['model']), 'reasoning_effort': spec.get('reasoning_effort'),
            'requested_service_tier': spec.get('service_tier'), 'service_tier': None,
            'session_service_tier': response.get('serviceTier'), 'usage': normalized, 'codex_usage': usage,
            'cost_usd': None, 'auth': 'chatgpt', 'transport': 'app-server',
            'server_start_ms': startup_ms, 'thread_start_ms': thread_ms, 'first_token_ms': first_token_ms,
            'server_turn_ms': completed.get('durationMs'), 'duration_ms': (time.perf_counter() - started) * 1000}


class CodexServerProvider:
    supports_streaming = True

    def __init__(self, config):
        self.config = config
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.thread = None
        self.lock = threading.Lock()
        self.closed = False

    def ensure_host(self):
        with self.lock:
            if self.closed:
                raise RuntimeError('Codex provider is closed')
            if self.thread:
                return
            self.client = AppServerClient(self.config)
            self.thread = threading.Thread(target=self.loop.run_forever, name='codex-app-server', daemon=True)
            self.thread.start()

    async def generate(self, role, stage, question, draft=None, independent=None, case=None, on_delta=None):
        self.ensure_host()
        caller = asyncio.get_running_loop()
        callback = (lambda delta: caller.call_soon_threadsafe(on_delta, delta)) if on_delta else None
        completed = threading.Event()
        async def invoke():
            try:
                return await self.client.generate(self.config[role], stage, question, draft, independent, callback)
            finally:
                completed.set()
        future = asyncio.run_coroutine_threadsafe(invoke(), self.loop)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            # Wait for the server-side interrupt/cleanup before this provider is reused.
            await asyncio.to_thread(completed.wait, 5)
            raise

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        if self.thread:
            async def shutdown():
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t is not self.client.reader]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await self.client.close()
            future = asyncio.run_coroutine_threadsafe(shutdown(), self.loop)
            future.result(timeout=5)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
        self.loop.close()
