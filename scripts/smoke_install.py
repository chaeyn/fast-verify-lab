"""Test the installed package from an empty folder. No provider credentials are used."""
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile

with tempfile.TemporaryDirectory(prefix='fast-verify-install-') as folder:
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['FAST_VERIFY_CONFIG'] = str(Path(folder) / 'absent-config.json')
    env['FAST_VERIFY_RESULTS_DIR'] = str(Path(folder) / 'results')
    def command(*args):
        completed = subprocess.run([sys.executable, '-m', 'fast_verify_lab', *args],
                                   cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        if completed.returncode:
            raise AssertionError(f'{args}: {completed.stderr}\n{completed.stdout}')
        return completed.stdout
    version = command('--version').strip()
    executable = Path(sysconfig.get_path('scripts')) / ('fast-verify.exe' if os.name == 'nt' else 'fast-verify')
    installed = subprocess.run([str(executable), '--version'], cwd=folder, env=env, capture_output=True,
                               text=True, encoding='utf-8', timeout=10)
    assert installed.returncode == 0 and installed.stdout.strip() == version, installed.stderr
    output = command('demo', '--provider', 'mock')
    events = [json.loads(line) for line in output.splitlines() if line.strip()]
    assert events[0]['event'] == 'draft', output
    assert events[-1]['status'] == 'corrected', output
    assert events[-1]['answer'] == '323', output
    answer = command('ask', '--provider', 'mock', '--case', 'multiply', '--json', '--no-save')
    assert json.loads(answer.splitlines()[-1])['status'] == 'corrected', answer
    assert not (Path(folder) / 'results').exists(), 'The --no-save option created a result folder'
    command('bench', '--provider', 'mock', '--repeats', '1', '--output', str(Path(folder) / 'benchmark'))
    assert list((Path(folder) / 'benchmark').rglob('summary.json'))
    print(f'Installed package smoke passed: {version}; console and module commands; bundled cases; demo; ask; benchmark.')
