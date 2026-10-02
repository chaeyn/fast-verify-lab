"""Test saved and piped shell installs from a local release fixture."""
from contextlib import contextmanager
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_RELEASE_ROOT = 'https://github.com/chaeyn/fast-verify-lab/releases/download'


@contextmanager
def serve_release(directory):
    """Serve only the temporary release directory over loopback."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = http.server.ThreadingHTTPServer(
        ('127.0.0.1', 0), functools.partial(Handler, directory=str(directory)))
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def local_installer(release_root):
    """Change the release URL only. Keep the version and installer code intact."""
    source = (ROOT / 'install-release.sh').read_text(encoding='utf-8')
    original = f"RELEASE_ROOT = {OFFICIAL_RELEASE_ROOT!r}"
    if source.count(original) != 1:
        raise AssertionError('Expected one release URL constant in install-release.sh')
    return source.replace(original, f'RELEASE_ROOT = {release_root!r}')


def main():
    if os.name == 'nt':
        print('Release shell smoke skipped on native Windows.')
        return
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/smoke_release_install.py PATH_TO_WHEEL')
    wheel = Path(sys.argv[1]).resolve(strict=True)
    version = wheel.name.split('-')[1]
    with tempfile.TemporaryDirectory(prefix="fast-verify release ' 한글 ") as temporary:
        folder = Path(temporary).resolve()
        releases = folder / 'releases'
        release = releases / f'v{version}'
        release.mkdir(parents=True)
        shutil.copyfile(wheel, release / wheel.name)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        (release / 'SHA256SUMS').write_text(f'{digest}  {wheel.name}\n', encoding='ascii')
        caller = folder / 'outside checkout'
        caller.mkdir()
        with serve_release(releases) as release_root:
            source = local_installer(release_root)
            installer = folder / 'downloaded installer.sh'
            installer.write_text(source, encoding='utf-8')
            for mode in ('saved', 'piped'):
                environment = os.environ.copy()
                for name in ('PYTHONPATH', 'PYTHONHOME', 'FAST_VERIFY_INSTALL_DIR', 'FAST_VERIFY_BIN_DIR'):
                    environment.pop(name, None)
                environment.update(
                    FAST_VERIFY_PYTHON=sys.executable,
                    FAST_VERIFY_INSTALL_DIR=str(folder / mode / 'app'),
                    FAST_VERIFY_BIN_DIR=str(folder / mode / 'bin'),
                    FAST_VERIFY_CONFIG=str(folder / mode / 'absent-config.json'),
                    FAST_VERIFY_RESULTS_DIR=str(folder / mode / 'results'),
                    PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')

                def run(arguments, input=None):
                    result = subprocess.run(arguments, input=input, cwd=caller, env=environment,
                                            capture_output=True, text=True, encoding='utf-8', timeout=90)
                    if result.returncode:
                        raise AssertionError(f'{mode}: {arguments}: {result.stderr}\n{result.stdout}')
                    return result.stdout

                if mode == 'saved':
                    run(['sh', str(installer)])
                else:
                    run(['sh'], input=source)
                launcher = str(folder / mode / 'bin' / 'fast-verify')
                installed_version = run([launcher, '--version']).strip()
                if version not in installed_version:
                    raise AssertionError(f'Unexpected installed version: {installed_version}')
                demo = [json.loads(line) for line in run([launcher, 'demo']).splitlines() if line.strip()]
                assert demo[0]['event'] == 'draft' and demo[-1]['answer'] == '323', demo
                answer = run([launcher, 'ask', '--provider', 'mock', '--case', 'multiply', '--json', '--no-save'])
                events = [json.loads(line) for line in answer.splitlines() if line.strip()]
                assert events[-1]['status'] == 'corrected' and events[-1]['answer'] == '323', events
                assert not (folder / mode / 'results').exists(), 'A no-save command created result files'
                print(f'{mode} shell installation passed: {installed_version}; demo; JSON ask; no result files.')


if __name__ == '__main__':
    main()
