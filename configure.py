"""Interactive connection setup and local diagnostics. No third-party dependencies."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from .providers import DEFAULTS, load_config
    from .paths import config_path, configure_stdio
else:
    from providers import DEFAULTS, load_config
    from paths import config_path, configure_stdio

ROOT = Path(__file__).parent
CHOICES = ('codex', 'claude', 'openai', 'anthropic', 'api')


def ask(prompt, default='', read=input):
    return read(f'{prompt}' + (f' [{default}]' if default else '') + ': ').strip() or default


def choose_role(role, read=input):
    print(f'\n{role}: choose a connection')
    print('  1 Codex login   2 Claude Code login   3 OpenAI API   4 Claude API   5 Compatible API')
    while True:
        choice = ask('Connection number', '1', read)
        if choice in ('1', '2', '3', '4', '5'):
            break
        print('Enter a number from 1 to 5.')
    provider = CHOICES[int(choice) - 1]
    defaults = {'codex': ('gpt-6-luna', 'gpt-6.1-sol'), 'claude': ('haiku', 'sonnet')}
    default = defaults.get(provider, ('', ''))[0 if role == 'Draft' else 1]
    model = ask('Model ID (must be available to your account)', default, read)
    while not model:
        model = ask('Model ID is required', read=read)
    spec = {'provider': provider, 'model': model}
    if provider == 'codex':
        spec['service_tier'] = 'fast' if role == 'Draft' else 'standard'
    if provider in ('codex', 'claude', 'openai'):
        effort = ask('Reasoning effort (leave empty for provider default)',
                     ('low' if role == 'Draft' else 'high') if provider == 'codex' else '', read)
        if effort:
            spec['reasoning_effort'] = effort
    if provider in ('openai', 'anthropic', 'api'):
        base = 'https://api.anthropic.com/v1' if provider == 'anthropic' else 'https://api.openai.com/v1'
        spec['base_url'] = ask('API base URL (include /v1 when required)', base, read)
        spec['api_key_env'] = ask('Environment variable name for API key (do not paste the key)',
                                  'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY', read)
        while not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', spec['api_key_env']):
            print('Enter a variable name such as OPENAI_API_KEY, not the key value.')
            spec['api_key_env'] = ask('Environment variable name', read=read)
    return spec


def wizard(path=None, read=input):
    path = config_path(path=path)
    print('\nFAST VERIFY LAB · Connection setup')
    print('Show a fast draft, then review it. Accepted drafts are not repeated.')
    print('API calls use API billing. CLI calls use the login managed by each CLI.')
    print('Configuration saves model IDs and connection settings, never API keys.')
    config = {'timeout_seconds': 120, 'max_output_tokens': 4096,
              'fast': choose_role('Draft', read), 'strong': choose_role('Review', read)}
    print('\nDraft: {provider} / {model}'.format(**config['fast']))
    print('Review: {provider} / {model}'.format(**config['strong']))
    path = Path(path)
    if path.exists() and ask(f'Replace {path.name}? y/N', 'n', read).lower() != 'y':
        print('Configuration unchanged.')
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    print(f'\nSaved {path}. Run fast-verify doctor, then fast-verify tui.')
    return path


def doctor(path, provider=None):
    provider = provider or next((name for name, filename in DEFAULTS.items()
        if filename == Path(path).name and name not in ('configured', 'mock')), None)
    config = load_config('configured', path)
    ok = True
    print(f'Python {sys.version.split()[0]} · Config: {Path(path).resolve()}')
    try:
        import curses
    except ImportError:
        print('TUI support: unavailable. Install the tui extra on Windows or a Python build with curses on Unix.')
    else:
        print('TUI support: installed (an interactive terminal is required).')
    for role in ('fast', 'strong'):
        spec = config[role]
        name = spec.get('provider', provider or 'not configured')
        print(f'{role}: {name} / {spec.get("model", "missing model")}')
        if not isinstance(spec.get('model'), str) or not spec['model'] or spec['model'].startswith('SET_'):
            print('  Missing model ID. Run fast-verify setup.'); ok = False
        if name in ('codex', 'claude'):
            binary = shutil.which(name)
            if not binary:
                print(f'  Missing CLI: install {name} and sign in.'); ok = False; continue
            command = [binary, 'login', 'status'] if name == 'codex' else [binary, 'auth', 'status']
            try:
                result = subprocess.run(command, capture_output=True, timeout=15)
                print('  CLI installed · ' + ('login detected' if result.returncode == 0 else 'login required'))
                ok &= result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                print('  Could not check login.'); ok = False
        elif name in ('api', 'openai', 'anthropic'):
            env = spec.get('api_key_env', config.get('api_key_env', 'ANTHROPIC_API_KEY' if name == 'anthropic' else 'OPENAI_API_KEY'))
            present = bool(os.environ.get(env))
            print(f'  {env}: ' + ('set' if present else 'missing')); ok &= present
        elif name != 'mock':
            print('  Unknown provider.'); ok = False
    print('Local checks only; model access, billing and API connectivity require a real run.')
    return ok


def main(argv=None):
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--doctor', action='store_true')
    parser.add_argument('--provider', choices=CHOICES, help='Provider for a legacy single-provider config')
    args = parser.parse_args(argv)
    try:
        if args.doctor:
            raise SystemExit(0 if doctor(config_path(args.provider or 'configured', args.config), args.provider) else 1)
        wizard(args.config)
    except (EOFError, KeyboardInterrupt):
        print('\nSetup cancelled.'); raise SystemExit(130)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f'Setup failed: {exc}\n')


if __name__ == '__main__':
    main()
