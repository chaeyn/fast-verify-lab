"""Read bundled resources and choose writable per-user locations."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
APP_NAME = 'fast-verify-lab'
PRESETS = {'codex': 'config.codex.json', 'mock': 'config.example.json',
           'openai': 'config.example.json', 'anthropic': 'config.anthropic.json',
           'claude': 'config.claude.json', 'api': 'config.api.json'}


def user_config_dir():
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming')) / APP_NAME
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / APP_NAME
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / APP_NAME


def user_results_dir():
    override = os.environ.get('FAST_VERIFY_RESULTS_DIR')
    if override:
        return Path(override).expanduser()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / APP_NAME
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support' / APP_NAME
    else:
        base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) / APP_NAME
    return base / 'results'


def config_path(name='configured', path=None):
    if path is not None:
        return Path(path).expanduser()
    if name != 'configured':
        return ROOT / PRESETS[name]
    override = os.environ.get('FAST_VERIFY_CONFIG')
    if override:
        return Path(override).expanduser()
    local = Path.cwd() / 'config.local.json'
    return local if local.is_file() else user_config_dir() / 'config.json'


def cases_path():
    return ROOT / 'data' / 'cases.jsonl'


def configure_stdio():
    """Use UTF-8 for text commands, including redirected Windows streams."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
