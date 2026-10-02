"""Check POSIX launchers without downloads or changes to the user's environment."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SH = shutil.which('sh')

# The interpreter records calls and creates a small, isolated virtual environment.
# Python probes execute as written. Only venv creation, pip, and the app are faked.
FAKE_PYTHON = r'''import json
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
executable = Path(sys.argv[0]).resolve()
environment = executable.parent.parent
with open(os.environ['SHELL_TEST_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps({'args': args, 'cwd': os.getcwd(),
                          'executable': str(executable)}, ensure_ascii=False) + '\n')
if os.environ.get('SHELL_TEST_OLD_PYTHON') == '1':
    sys.version_info = (3, 10, 0)
if args[:1] == ['-c']:
    if (environment / '.installed').exists():
        sys.path.insert(0, os.environ['SHELL_TEST_PACKAGES'])
    sys.prefix = str(environment)
    exec(args[1])
elif args[:2] == ['-m', 'venv']:
    destination = Path(args[-1])
    (destination / 'bin').mkdir(parents=True)
    (destination / 'pyvenv.cfg').write_text('home = test-fixture\n')
    for name in ('python', 'python3'):
        target = destination / 'bin' / name
        shutil.copyfile(executable, target)
        target.chmod(0o755)
elif args[:3] == ['-m', 'pip', '--version']:
    print('pip fixture')
elif args[:3] == ['-m', 'pip', 'install']:
    print('Fixture pip progress goes to stderr through the installer.')
    failure = int(os.environ.get('SHELL_TEST_PIP_EXIT', '0'))
    if failure:
        sys.exit(failure)
    (environment / '.installed').touch()
elif args[:2] == ['-m', 'fast_verify_lab']:
    if not (environment / '.installed').exists():
        sys.exit('The fixture app is not installed.')
    print(json.dumps({'args': args[2:], 'cwd': os.getcwd()}, ensure_ascii=False))
    sys.exit(int(os.environ.get('SHELL_TEST_APP_EXIT', '0')))
else:
    sys.exit('Unexpected fixture invocation: ' + repr(args))
'''


@unittest.skipIf(os.name == 'nt' or SH is None, 'POSIX shell launchers require sh')
class ShellLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fast-verify shell ')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.repo = self.folder / 'repository with spaces'
        self.repo.mkdir()
        for name in ('install.sh', 'run.sh', 'pyproject.toml'):
            shutil.copyfile(ROOT / name, self.repo / name)
        self.caller = self.folder / 'caller 한국어'
        self.caller.mkdir()
        (self.caller / 'config.local.json').write_text('{}', encoding='utf-8')
        self.log = self.folder / 'calls.jsonl'
        self.interpreter = self.folder / 'Python fixture'
        # Exclude the test runner's site-packages. CI installs the real app there,
        # but the fixture must expose it only after its own pip install succeeds.
        self.interpreter.write_text(f'#!{sys.executable} -S\n' + FAKE_PYTHON, encoding='utf-8')
        self.interpreter.chmod(0o755)
        packages = self.folder / 'packages'
        (packages / 'fast_verify_lab').mkdir(parents=True)
        (packages / 'fast_verify_lab' / '__init__.py').touch()
        self.env = os.environ.copy()
        for name in ('FAST_VERIFY_PYTHON', 'FAST_VERIFY_VENV', 'PYTHONPATH', 'PYTHONHOME'):
            self.env.pop(name, None)
        self.env.update(FAST_VERIFY_PYTHON=str(self.interpreter),
                        SHELL_TEST_LOG=str(self.log), SHELL_TEST_PACKAGES=str(packages))

    def run_script(self, name, *args, **environment):
        return subprocess.run([SH, str(self.repo / name), *args], cwd=self.caller,
                              env={**self.env, **environment}, capture_output=True,
                              text=True, encoding='utf-8', timeout=10)

    def calls(self, *prefix):
        if not self.log.exists():
            return []
        calls = [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()]
        return [call for call in calls if call['args'][:len(prefix)] == list(prefix)]

    def create_environment(self, installed=False):
        destination = self.repo / '.venv'
        (destination / 'bin').mkdir(parents=True)
        (destination / 'pyvenv.cfg').write_text('home = test-fixture\n', encoding='utf-8')
        shutil.copyfile(self.interpreter, destination / 'bin' / 'python')
        (destination / 'bin' / 'python').chmod(0o755)
        if installed:
            (destination / '.installed').touch()
        return destination

    def test_install_resolves_relative_environment_from_repository(self):
        process = self.run_script('install.sh', FAST_VERIFY_VENV='runtime env')
        self.assertEqual(process.returncode, 0, process.stderr)
        destination = self.repo / 'runtime env'
        self.assertTrue((destination / 'pyvenv.cfg').is_file())
        self.assertFalse((self.caller / 'runtime env').exists())
        self.assertEqual(len(self.calls('-m', 'venv')), 1)
        installs = self.calls('-m', 'pip', 'install')
        self.assertEqual(len(installs), 1)
        self.assertIn(str(self.repo) + '[tui]', installs[0]['args'])
        self.assertEqual(process.stdout, '')
        self.assertIn('Fixture pip progress', process.stderr)

    def test_explicit_install_reuses_existing_environment(self):
        for _ in range(2):
            process = self.run_script('install.sh')
            self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(len(self.calls('-m', 'venv')), 1)
        self.assertEqual(len(self.calls('-m', 'pip', 'install')), 2)

    def test_first_run_installs_and_starts_tui_without_polluting_stdout(self):
        process = self.run_script('run.sh')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), {'args': ['tui'], 'cwd': str(self.caller)})
        self.assertEqual(len(self.calls('-m', 'venv')), 1)
        self.assertEqual(len(self.calls('-m', 'pip', 'install')), 1)
        self.assertIn('Fixture pip progress', process.stderr)

    def test_installed_run_preserves_arguments_cwd_and_exit_code(self):
        self.create_environment(installed=True)
        arguments = ('ask', '공백과 "quotes" and $literal\nsecond line', '--json', '--no-save')
        process = self.run_script('run.sh', *arguments, SHELL_TEST_APP_EXIT='23')
        self.assertEqual(process.returncode, 23, process.stderr)
        self.assertEqual(json.loads(process.stdout), {'args': list(arguments), 'cwd': str(self.caller)})
        self.assertEqual(self.calls('-m', 'venv'), [])
        self.assertEqual(self.calls('-m', 'pip', 'install'), [])

    def test_repeated_run_does_not_reinstall(self):
        for _ in range(2):
            process = self.run_script('run.sh', 'doctor')
            self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(len(self.calls('-m', 'pip', 'install')), 1)
        self.assertEqual(len(self.calls('-m', 'fast_verify_lab')), 2)

    def test_run_installs_package_into_existing_empty_environment(self):
        self.create_environment()
        process = self.run_script('run.sh', '--version')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['args'], ['--version'])
        self.assertEqual(self.calls('-m', 'venv'), [])
        self.assertEqual(len(self.calls('-m', 'pip', 'install')), 1)

    def test_failed_install_preserves_exit_status_and_does_not_launch(self):
        for script in ('install.sh', 'run.sh'):
            with self.subTest(script=script):
                process = self.run_script(script, SHELL_TEST_PIP_EXIT='42')
                self.assertEqual(process.returncode, 42, process.stderr)
                self.assertEqual(process.stdout, '')
        self.assertEqual(self.calls('-m', 'fast_verify_lab'), [])

    def test_help_does_not_require_python_or_create_environment(self):
        for script in ('install.sh', 'run.sh'):
            with self.subTest(script=script):
                process = self.run_script(script, '--help', FAST_VERIFY_PYTHON='/missing/python')
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIn('Usage', process.stdout + process.stderr)
        self.assertFalse((self.repo / '.venv').exists())
        self.assertEqual(self.calls(), [])

    def test_missing_selected_interpreter_reports_error(self):
        process = self.run_script('install.sh', FAST_VERIFY_PYTHON='/missing/python')
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('Python', process.stderr)
        self.assertEqual(process.stdout, '')
        self.assertEqual(self.calls('-m', 'venv'), [])

    def test_old_interpreter_reports_required_version(self):
        process = self.run_script('install.sh', SHELL_TEST_OLD_PYTHON='1')
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('3.11', process.stderr)
        self.assertEqual(process.stdout, '')
        self.assertEqual(self.calls('-m', 'venv'), [])


if __name__ == '__main__':
    unittest.main()
