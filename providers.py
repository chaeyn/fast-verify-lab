"""Additional transports and per-role routing; credentials stay in the environment."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.error
import urllib.request

if __package__:
    from .lab import REVIEW, SOLVE, ProviderError
    from .process_utils import process_options, stop_process_tree
else:
    from lab import REVIEW, SOLVE, ProviderError
    from process_utils import process_options, stop_process_tree

PROVIDERS = ('codex', 'mock', 'openai', 'anthropic', 'claude', 'api', 'configured')
DEFAULTS = {'codex': 'config.codex.json', 'mock': 'config.example.json',
            'openai': 'config.example.json', 'anthropic': 'config.anthropic.json',
            'claude': 'config.claude.json', 'api': 'config.api.json', 'configured': 'config.local.json'}


def load_config(name, path=None):
    if __package__:
        from .paths import config_path
    else:
        from paths import config_path
    config = json.loads(config_path(name, path).read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Config must be a JSON object')
    def has_secret(value):
        if isinstance(value, dict):
            return any(k.lower() in ('api_key', 'token', 'access_token') or has_secret(v) for k, v in value.items())
        return isinstance(value, list) and any(has_secret(item) for item in value)
    if has_secret(config):
        raise ValueError('Keep credentials in environment variables, not config files')
    return config


class HTTPProvider:
    def __init__(self, config, kind):
        self.config, self.kind = config, kind
        self.key_env = config.get('api_key_env', 'ANTHROPIC_API_KEY' if kind == 'anthropic' else 'OPENAI_API_KEY')
        self.key = os.environ.get(self.key_env)
        if not self.key:
            raise ValueError(f'Set {self.key_env} before running {kind}. See GUIDE.md.')
        for role in ('fast', 'strong'):
            model = config[role].get('model')
            if not isinstance(model, str) or not model.strip() or model.startswith('SET_'):
                raise ValueError('Set fast.model and strong.model in your config. Run fast-verify setup.')

    def request(self, payload):
        base = self.config.get('base_url', 'https://api.anthropic.com/v1' if self.kind == 'anthropic' else 'https://api.openai.com/v1')
        suffix = '/messages' if self.kind == 'anthropic' else '/chat/completions'
        headers = {'Content-Type': 'application/json'}
        if self.kind == 'anthropic':
            headers.update({'x-api-key': self.key, 'anthropic-version': '2023-06-01'})
        else:
            headers['Authorization'] = 'Bearer ' + self.key
        request = urllib.request.Request(base.rstrip('/') + suffix, data=json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.config.get('timeout_seconds', 90)) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProviderError(f'API HTTP {code}') from None
        except (urllib.error.URLError, TimeoutError):
            raise ProviderError('API connection failed or timed out') from None
        except (ValueError, UnicodeError):
            raise ProviderError('API returned invalid JSON') from None

    async def generate(self, role, stage, question, draft=None, independent=None, case=None):
        spec = self.config[role]
        system = REVIEW if stage == 'review' else SOLVE
        prompt = json.dumps({'question': question, 'draft': draft, 'independent_answer': independent}, ensure_ascii=False)
        payload = {'model': spec['model'], 'max_tokens': self.config.get('max_output_tokens', 4096)}
        if self.kind == 'anthropic':
            payload.update(system=system, messages=[{'role': 'user', 'content': prompt}])
        else:
            payload['messages'] = [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]
            # Opt in because some compatible servers do not implement JSON mode.
            if stage == 'review' and self.config.get('json_mode', False):
                payload['response_format'] = {'type': 'json_object'}
        started = time.perf_counter()
        data = await asyncio.to_thread(self.request, payload)
        if not isinstance(data, dict):
            raise ProviderError('API returned an invalid response')
        raw = data.get('usage') or {}
        if self.kind == 'anthropic':
            if data.get('stop_reason') != 'end_turn' or any(c.get('type') == 'tool_use' for c in data.get('content', [])):
                raise ProviderError('Claude did not finish an answer without tools')
            answer = ''.join(c['text'] for c in data.get('content', []) if c.get('type') == 'text')
            cached = raw.get('cache_read_input_tokens', 0)
            usage = None if not raw else {'input_tokens': raw.get('input_tokens', 0) + cached + raw.get('cache_creation_input_tokens', 0),
                'output_tokens': raw.get('output_tokens', 0), 'input_tokens_details': {'cached_tokens': cached}}
        else:
            choice = (data.get('choices') or [{}])[0]
            if choice.get('finish_reason') != 'stop' or choice.get('message', {}).get('tool_calls'):
                raise ProviderError('Compatible API returned an incomplete answer')
            answer = choice.get('message', {}).get('content')
            usage = None if not raw else {'input_tokens': raw.get('prompt_tokens', 0), 'output_tokens': raw.get('completion_tokens', 0),
                'input_tokens_details': {'cached_tokens': raw.get('prompt_tokens_details', {}).get('cached_tokens', 0)}}
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderError('API returned no answer text')
        return {'text': answer, 'model': data.get('model'), 'requested_model': spec['model'], 'response_id': data.get('id'),
                'usage': usage, 'cost_usd': None, 'provider': self.kind, 'duration_ms': (time.perf_counter() - started) * 1000}


class ClaudeProvider:
    """Use the official Claude Code CLI login; no token extraction."""
    def __init__(self, config):
        self.config = config
        self.binary = shutil.which('claude')
        if not self.binary:
            raise ValueError('Install Claude Code and run claude auth login. See GUIDE.md.')
        for role in ('fast', 'strong'):
            model = config[role].get('model')
            if not isinstance(model, str) or not model.strip() or model.startswith('SET_'):
                raise ValueError('Set fast.model and strong.model in your config. Run fast-verify setup.')

    async def generate(self, role, stage, question, draft=None, independent=None, case=None):
        spec = self.config[role]
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix='fast-verify-claude-') as folder:
            command = [self.binary, '-p', '--safe-mode', '--output-format', 'json', '--no-session-persistence',
                       '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                       '--setting-sources', '', '--disable-slash-commands',
                       '--settings', '{"disableAllHooks":true}',
                       '--system-prompt', REVIEW if stage == 'review' else SOLVE, '--model', spec['model']]
            if spec.get('reasoning_effort'):
                command += ['--effort', spec['reasoning_effort']]
            env = os.environ.copy()
            for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_OAUTH_TOKEN',
                         'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY', 'CLAUDE_CODE_SIMPLE'):
                env.pop(name, None)
            process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=folder, env=env, **process_options())
            prompt = json.dumps({'question': question, 'draft': draft, 'independent_answer': independent}, ensure_ascii=False)
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(prompt.encode()), self.config.get('timeout_seconds', 120))
            except (asyncio.CancelledError, TimeoutError):
                await stop_process_tree(process)
                await process.communicate()
                raise
            if process.returncode:
                raise ProviderError(f'Claude Code exited with code {process.returncode}')
            try:
                data = json.loads(stdout)
            except (ValueError, UnicodeError):
                raise ProviderError('Claude Code returned invalid JSON') from None
            if (not isinstance(data, dict) or data.get('is_error') or data.get('subtype') != 'success'
                    or not isinstance(data.get('result'), str) or not data['result'].strip()):
                raise ProviderError('Claude Code did not complete with an answer')
        raw = data.get('usage') or {}
        cached = raw.get('cache_read_input_tokens', 0)
        usage = None if not raw else {'input_tokens': raw.get('input_tokens', 0) + cached + raw.get('cache_creation_input_tokens', 0),
            'output_tokens': raw.get('output_tokens', 0), 'input_tokens_details': {'cached_tokens': cached}}
        return {'text': data['result'], 'model': None, 'requested_model': spec['model'], 'usage': usage,
                'cost_usd': None, 'provider': 'claude', 'duration_ms': (time.perf_counter() - started) * 1000}


class RoleProvider:
    """Lazy per-role connections let a Codex draft be reviewed by Claude, or vice versa."""
    supports_streaming = True

    def __init__(self, config):
        self.config, self.clients = config, {}
        for role in ('fast', 'strong'):
            if config[role].get('provider') not in PROVIDERS[:-1]:
                raise ValueError(f'Set {role}.provider to codex, claude, openai, anthropic, api, or mock')

    def client(self, role):
        if __package__:
            from .lab import make_provider
        else:
            from lab import make_provider
        connection_fields = ('base_url', 'api_key_env', 'transport', 'timeout_seconds', 'max_output_tokens', 'json_mode')
        spec = self.config[role]
        connection = {k:v for k,v in self.config.items() if k not in ('fast', 'strong')}
        connection.update({k:v for k,v in spec.items() if k in connection_fields})
        key = (spec['provider'], json.dumps(connection, sort_keys=True))
        if key not in self.clients:
            merged = dict(connection)
            for other in ('fast', 'strong'):
                candidate = self.config[other]
                settings = {k:v for k,v in self.config.items() if k not in ('fast', 'strong')}
                settings.update({k:v for k,v in candidate.items() if k in connection_fields})
                merged[other] = candidate if candidate['provider'] == spec['provider'] and settings == connection else spec
            self.clients[key] = make_provider(spec['provider'], merged)
        return self.clients[key]

    def prepare(self, mode):
        for role in (('fast',) if mode == 'fast' else ('strong',) if mode == 'strong' else ('fast', 'strong')):
            self.client(role)

    async def generate(self, role, stage, question, **kwargs):
        client = self.client(role)
        if not getattr(client, 'supports_streaming', False):
            kwargs.pop('on_delta', None)
        result = await client.generate(role, stage, question, **kwargs)
        result['provider'] = self.config[role]['provider']
        return result

    def close(self):
        for client in self.clients.values():
            if hasattr(client, 'close'):
                client.close()
