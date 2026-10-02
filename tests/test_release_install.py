"""Check release download, verification, isolation, and launcher behavior offline."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.smoke_release_install import local_installer, serve_release


VERSION = '0.1.2'
WHEEL_NAME = f'fast_verify_lab-{VERSION}-py3-none-any.whl'
SH = shutil.which('sh')


def make_wheel(path):
    """Build a small valid wheel so tests can use real venv and pip offline."""
    module = ('import json, os, sys\n'
              'result = {"args": sys.argv[1:], "cwd": os.getcwd()}\n'
              'if sys.argv[1:] == ["echo-stdin"]:\n'
              '    result["stdin"] = sys.stdin.read()\n'
              '    print("fixture stderr", file=sys.stderr)\n'
              'print(json.dumps(result, ensure_ascii=False))\n'
              'sys.exit(int(os.environ.get("RELEASE_TEST_EXIT", "0")))\n')
    dist = f'fast_verify_lab-{VERSION}.dist-info'
    files = {
        'fast_verify_lab/__init__.py': f'__version__ = {VERSION!r}\n',
        'fast_verify_lab/__main__.py': module,
        f'{dist}/METADATA': f'Metadata-Version: 2.1\nName: fast-verify-lab\nVersion: {VERSION}\nRequires-Python: >=3.11\n',
        f'{dist}/WHEEL': 'Wheel-Version: 1.0\nGenerator: release-installer-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
    }
    files[f'{dist}/RECORD'] = ''.join(f'{name},,\n' for name in files) + f'{dist}/RECORD,,\n'
    with zipfile.ZipFile(path, 'w') as wheel:
        for name, contents in files.items():
            wheel.writestr(name, contents)


@unittest.skipIf(os.name == 'nt' or SH is None, 'Release shell installation requires POSIX sh')
class ReleaseInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fast-verify release ' 한글 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.releases = self.folder / 'releases'
        self.release = self.releases / f'v{VERSION}'
        self.release.mkdir(parents=True)
        self.wheel = self.release / WHEEL_NAME
        make_wheel(self.wheel)
        self.manifest = self.release / 'SHA256SUMS'
        digest = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        self.manifest.write_text(f'{digest}  {WHEEL_NAME}\n', encoding='ascii')
        server = serve_release(self.releases)
        release_root = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.installer = self.folder / 'installer.sh'
        self.installer.write_text(local_installer(release_root), encoding='utf-8')
        self.install_dir = self.folder / 'application'
        self.bin_dir = self.folder / 'commands'
        self.caller = self.folder / 'outside checkout'
        self.caller.mkdir()
        self.environment = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME'):
            self.environment.pop(name, None)
        self.environment.update(
            FAST_VERIFY_PYTHON=sys.executable,
            FAST_VERIFY_INSTALL_DIR=str(self.install_dir),
            FAST_VERIFY_BIN_DIR=str(self.bin_dir),
            PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')

    def install(self, *args, **environment):
        return subprocess.run([SH, str(self.installer), *args], cwd=self.caller,
                              env={**self.environment, **environment}, capture_output=True,
                              text=True, encoding='utf-8', timeout=60)

    def assert_no_install(self):
        self.assertFalse(self.install_dir.exists())
        self.assertFalse(self.bin_dir.exists())

    def test_help_does_not_require_python_or_install(self):
        self.manifest.unlink()
        result = self.install('--help', FAST_VERIFY_PYTHON='/missing/python')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Usage', result.stdout + result.stderr)
        self.assert_no_install()

    def test_missing_selected_python_reports_error(self):
        result = self.install(FAST_VERIFY_PYTHON='/missing/python')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('3.11', result.stderr)
        self.assert_no_install()

    def test_old_python_reports_required_version(self):
        interpreter = self.folder / 'old-python'
        interpreter.write_text('#!/bin/sh\nexit 1\n', encoding='ascii')
        interpreter.chmod(0o755)
        result = self.install(FAST_VERIFY_PYTHON=str(interpreter))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('3.11', result.stderr)
        self.assert_no_install()

    def test_checksum_failure_does_not_create_installation(self):
        self.manifest.write_text(f'{"0" * 64}  {WHEEL_NAME}\n', encoding='ascii')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr.lower(), 'checksum|sha-?256')
        self.assert_no_install()

    def test_manifest_without_wheel_does_not_install(self):
        self.manifest.write_text(f'{"0" * 64}  unrelated.whl\n', encoding='ascii')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_install()

    def test_http_failure_does_not_create_installation(self):
        self.wheel.unlink()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Could not download', result.stderr)
        self.assertIn(WHEEL_NAME, result.stderr)
        self.assert_no_install()

    def test_existing_unrelated_launcher_is_preserved(self):
        self.bin_dir.mkdir()
        launcher = self.bin_dir / 'fast-verify'
        launcher.write_text('my existing command\n', encoding='utf-8')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(launcher.read_text(encoding='utf-8'), 'my existing command\n')
        self.assertFalse(self.install_dir.exists())

    def test_existing_unrelated_install_directory_is_preserved(self):
        self.install_dir.mkdir()
        existing = self.install_dir / 'user-file'
        existing.write_text('keep this\n', encoding='utf-8')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'keep this\n')
        self.assertEqual(list(self.install_dir.iterdir()), [existing])
        self.assertFalse(self.bin_dir.exists())

    def test_relative_directories_are_rejected(self):
        for name in ('FAST_VERIFY_INSTALL_DIR', 'FAST_VERIFY_BIN_DIR'):
            with self.subTest(variable=name):
                result = self.install(**{name: 'relative-directory'})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('absolute', result.stderr.lower())
        self.assert_no_install()
        self.assertFalse((self.caller / 'relative-directory').exists())

    def test_launcher_directory_can_be_inside_install_directory(self):
        nested_bin = self.install_dir / 'nested bin'
        result = self.install(FAST_VERIFY_BIN_DIR=str(nested_bin))
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = subprocess.run([str(nested_bin / 'fast-verify')], cwd=self.caller,
                                env=self.environment, capture_output=True,
                                text=True, encoding='utf-8', timeout=10)
        self.assertEqual(launch.returncode, 0, launch.stderr)
        self.assertEqual(json.loads(launch.stdout), {'args': ['tui'], 'cwd': str(self.caller)})

    def test_repeat_install_and_quoted_launcher_arguments(self):
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
        launcher = self.bin_dir / 'fast-verify'
        self.assertTrue(launcher.is_file())
        for args, exit_code in (([], 0), (['ask', '한글 "double" and \'single\' $literal\nnext line', '--json'], 23)):
            with self.subTest(args=args):
                result = subprocess.run([str(launcher), *args], cwd=self.caller,
                                        env={**self.environment, 'RELEASE_TEST_EXIT': str(exit_code)},
                                        capture_output=True, text=True, encoding='utf-8', timeout=10)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertEqual(json.loads(result.stdout), {'args': args or ['tui'], 'cwd': str(self.caller)})
        self.assertTrue((self.install_dir / 'venv' / 'pyvenv.cfg').is_file())
        echo = subprocess.run([str(launcher), 'echo-stdin'], cwd=self.caller, env=self.environment,
                              input='stdin 한국어\nsecond line', capture_output=True,
                              text=True, encoding='utf-8', timeout=10)
        self.assertEqual(echo.returncode, 0, echo.stderr)
        self.assertEqual(json.loads(echo.stdout)['stdin'], 'stdin 한국어\nsecond line')
        self.assertEqual(echo.stderr, 'fixture stderr\n')


if __name__ == '__main__':
    unittest.main()
