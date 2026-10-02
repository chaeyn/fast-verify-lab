#!/bin/sh
# Install a local copy for the current user from a GitHub release.
set -eu

case "${1-}" in
    -h|--help)
        printf '%s\n' 'Install Fast Verify Lab 0.1.2 from GitHub. Git is not required.

Usage:
  sh install-release.sh
  curl -fsSL https://github.com/chaeyn/fast-verify-lab/releases/latest/download/install-release.sh | sh

Requires Python 3.11 or newer with venv and HTTPS support.

Optional environment variables:
  FAST_VERIFY_PYTHON       Python executable name or path
  FAST_VERIFY_INSTALL_DIR Absolute app directory (default: ~/.local/share/fast-verify-lab)
  FAST_VERIFY_BIN_DIR     Absolute launcher directory (default: ~/.local/bin)

The installer checks SHA256SUMS before it installs the release wheel.
It creates a local Python environment and a fast-verify launcher.
It does not change shell profiles or open the terminal interface.' >&2
        exit 0
        ;;
    '') ;;
    *) printf '%s\n' 'Unknown argument. Run sh install-release.sh --help.' >&2; exit 2 ;;
esac
if [ "$#" -gt 0 ]; then
    printf '%s\n' 'This installer takes no arguments. Run sh install-release.sh --help.' >&2
    exit 2
fi

fast_verify_python=''
if [ -n "${FAST_VERIFY_PYTHON-}" ]; then
    if command -v "$FAST_VERIFY_PYTHON" >/dev/null 2>&1 &&
       "$FAST_VERIFY_PYTHON" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        fast_verify_python=$FAST_VERIFY_PYTHON
    else
        printf '%s\n' 'FAST_VERIFY_PYTHON must select a working Python 3.11 or newer executable.' >&2
        exit 1
    fi
else
    for fast_verify_candidate in python3 python3.14 python3.13 python3.12 python3.11 python; do
        if command -v "$fast_verify_candidate" >/dev/null 2>&1 &&
           "$fast_verify_candidate" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            fast_verify_python=$fast_verify_candidate
            break
        fi
    done
fi
if [ -z "$fast_verify_python" ]; then
    printf '%s\n' 'Python 3.11 or newer was not found. Install Python with venv support, then run this installer again.' >&2
    exit 1
fi

exec "$fast_verify_python" -I - <<'FAST_VERIFY_INSTALLER_PYTHON'
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

VERSION = '0.1.2'
RELEASE_ROOT = 'https://github.com/chaeyn/fast-verify-lab/releases/download'
INSTALL_MARKER = '.fast-verify-managed'
MARKER_TEXT = 'fast-verify-lab github-release installer v1\n'
LAUNCHER_MARKER = '# fast-verify-lab managed launcher v1'


class InstallError(Exception):
    pass


def message(text):
    print(text, file=sys.stderr, flush=True)


def selected_path(name, default):
    value = os.environ.get(name)
    if value is not None and (not value or not Path(value).is_absolute()):
        raise InstallError(f'{name} must be an absolute path. The current value was not used.')
    # Do not expand a user override. A literal ~ is not an absolute path.
    return Path(os.path.abspath(value if value is not None else str(default)))


def install_state(directory):
    if directory.is_symlink():
        raise InstallError(f'Install directory is a symbolic link: {directory}. Select a separate directory.')
    if not directory.exists():
        return False
    if not directory.is_dir():
        raise InstallError(f'Install path is not a directory: {directory}. Select a separate directory.')
    marker = directory / INSTALL_MARKER
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise InstallError(f'Install marker is not a regular file: {marker}. Select a separate directory.')
    if marker.exists():
        if marker.read_text(encoding='utf-8') != MARKER_TEXT:
            raise InstallError(f'Install directory has an unknown marker: {directory}. Select a separate directory.')
        return True
    if any(directory.iterdir()):
        raise InstallError(f'Install directory contains unrelated files: {directory}. Select an empty directory.')
    return False


def launcher_header(directory):
    return '# install-dir: ' + json.dumps(str(directory), ensure_ascii=True)


def check_launcher(launcher, directory):
    if launcher.is_symlink():
        raise InstallError(f'Launcher is a symbolic link: {launcher}. Select a separate FAST_VERIFY_BIN_DIR.')
    if not launcher.exists():
        return
    if not launcher.is_file():
        raise InstallError(f'Launcher path is not a file: {launcher}. Select a separate FAST_VERIFY_BIN_DIR.')
    with launcher.open(encoding='utf-8') as existing:
        header = [existing.readline().rstrip('\n') for _ in range(3)]
    if header != ['#!/bin/sh', LAUNCHER_MARKER, launcher_header(directory)]:
        raise InstallError(f'Launcher belongs to another installation: {launcher}. Select a separate FAST_VERIFY_BIN_DIR.')


def run_command(command, detail):
    try:
        subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)
    except subprocess.CalledProcessError as exc:
        raise InstallError(f'{detail} (exit {exc.returncode}).') from None


def check_environment(environment):
    python = environment / 'bin' / 'python'
    if environment.is_symlink() or not environment.is_dir() or not (environment / 'pyvenv.cfg').is_file() or not python.exists():
        raise InstallError(f'Existing environment is incomplete or unrelated: {environment}. Select a new FAST_VERIFY_INSTALL_DIR.')
    check = ('import pathlib,sys; '
             'sys.exit(0 if sys.version_info >= (3,11) and sys.prefix != sys.base_prefix '
             'and pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve() else 1)')
    run_command([str(python), '-I', '-c', check, str(environment)],
                'The managed environment needs Python 3.11 or newer. Select a new FAST_VERIFY_INSTALL_DIR')
    return python


def download(url, target, maximum):
    request = urllib.request.Request(url, headers={'User-Agent': 'fast-verify-lab-installer/' + VERSION})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open('wb') as output:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > maximum:
                    raise InstallError('Release download exceeded its size limit. Check the release assets and try again.')
                output.write(chunk)
    except urllib.error.URLError as exc:
        raise InstallError(f'Could not download the release asset {target.name}: {exc.reason}. Check your network and the release page.') from None


def expected_hash(checksums, filename):
    matches = []
    for line in checksums.read_text(encoding='utf-8').splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == filename:
            if not re.fullmatch(r'[0-9a-fA-F]{64}', fields[0]):
                raise InstallError('SHA256SUMS has an invalid wheel checksum. Installation stopped.')
            matches.append(fields[0].lower())
    if len(matches) != 1:
        raise InstallError('SHA256SUMS must contain exactly one checksum for the release wheel. Installation stopped.')
    return matches[0]


def write_launcher(launcher, directory, python):
    check_launcher(launcher, directory)
    content = ('#!/bin/sh\n' + LAUNCHER_MARKER + '\n' + launcher_header(directory) + '\n'
               'if [ "$#" -eq 0 ]; then\n    set -- tui\nfi\n'
               'exec ' + shlex.quote(str(python)) + ' -I -m fast_verify_lab "$@"\n')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=launcher.parent,
                                         prefix='.fast-verify-', delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.chmod(0o755)
        os.replace(temporary, launcher)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    directory = selected_path('FAST_VERIFY_INSTALL_DIR', Path.home() / '.local' / 'share' / 'fast-verify-lab')
    bin_directory = selected_path('FAST_VERIFY_BIN_DIR', Path.home() / '.local' / 'bin')
    launcher = bin_directory / 'fast-verify'
    managed = install_state(directory)
    check_launcher(launcher, directory)
    environment = directory / 'venv'
    if environment.exists() or environment.is_symlink():
        if not managed:
            raise InstallError(f'Environment is not managed by this installer: {environment}. Select an empty directory.')
        python = check_environment(environment)
    else:
        python = environment / 'bin' / 'python'
    filename = f'fast_verify_lab-{VERSION}-py3-none-any.whl'
    release = f'{RELEASE_ROOT}/v{VERSION}'
    # Download and validate before creating an environment or invoking pip.
    with tempfile.TemporaryDirectory(prefix='fast-verify-download-') as downloads:
        wheel = Path(downloads) / filename
        sums = Path(downloads) / 'SHA256SUMS'
        message(f'Download Fast Verify Lab {VERSION}.')
        download(release + '/SHA256SUMS', sums, 1024 * 1024)
        checksum = expected_hash(sums, filename)
        download(release + '/' + filename, wheel, 64 * 1024 * 1024)
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != checksum:
            raise InstallError('Release wheel checksum does not match SHA256SUMS. Installation stopped before pip.')
        message('Release wheel checksum verified.')
        directory.mkdir(parents=True, exist_ok=True)
        # Recheck after downloads in case the destination changed during the request.
        managed = install_state(directory)
        check_launcher(launcher, directory)
        marker = directory / INSTALL_MARKER
        created_marker = not managed
        created_environment = False
        try:
            if created_marker:
                with marker.open('x', encoding='utf-8') as output:
                    output.write(MARKER_TEXT)
            bin_directory.mkdir(parents=True, exist_ok=True)
            if not environment.exists():
                created_environment = True
                run_command([sys.executable, '-I', '-m', 'venv', str(environment)],
                            'Could not create the environment. On Debian or Ubuntu, install the python3-venv package and retry')
            python = check_environment(environment)
            run_command([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check',
                         '--no-input', '--no-deps', '--no-index', '--upgrade', str(wheel)],
                        'Could not install the verified wheel. Check that the environment has pip and try again')
            version_check = ('import importlib.metadata,sys; '
                             'sys.exit(0 if importlib.metadata.version(\"fast-verify-lab\") == sys.argv[1] else 1)')
            run_command([str(python), '-I', '-c', version_check, VERSION],
                        'The installed package version does not match the release. Installation stopped')
            write_launcher(launcher, directory, python)
        except (InstallError, OSError, KeyboardInterrupt):
            # Remove only files created by this attempt. Preserve managed upgrades.
            if created_environment and environment.is_dir() and not environment.is_symlink():
                shutil.rmtree(environment)
            # Keep the ownership marker so a failed first install can be retried.
            raise
    message(f'Installed Fast Verify Lab {VERSION}.')
    message('Start the app: ' + shlex.quote(str(launcher)))
    message('Show command help: ' + shlex.quote(str(launcher)) + ' --help')
    if str(bin_directory) not in os.environ.get('PATH', '').split(os.pathsep):
        message('To use fast-verify by name in this terminal, run:')
        message('  export PATH=' + shlex.quote(str(bin_directory)) + ':"$PATH"')


try:
    main()
except KeyboardInterrupt:
    message('Installation cancelled. Run the installer again when ready.')
    raise SystemExit(130)
except (InstallError, OSError, ValueError) as exc:
    message('Install failed: ' + str(exc))
    raise SystemExit(1)
FAST_VERIFY_INSTALLER_PYTHON
