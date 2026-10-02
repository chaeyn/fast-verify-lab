# Testing

[Contributing](../CONTRIBUTING.md) · [Support](support.md)

## Run offline tests

Run from the repository root with Python 3.11 or later.

```sh
python -m pip install -e '.[tui,dev]'
python -m unittest discover -s tests -v
python scripts/check_docs.py
```

On Windows, use the Python executable in your virtual environment. The `tui` extra installs the curses dependency.

The suite uses local HTTP servers, fixed model responses, and CLI stubs. It does not need provider credentials or make paid model calls.

## What tests establish

| Area | Checks |
|---|---|
| Pipeline | Draft order, review states, independent answer, failure handling, exact grading |
| Routing | Different providers, endpoint settings, role settings, lazy client creation |
| HTTP | Request format, usage parsing, error redaction, incomplete answers |
| CLI adapters | Arguments, login isolation, answer parsing, timeout, cancellation |
| App Server | Process reuse, RPC routing, stream events, cancellation, disconnect |
| TUI | Prompt editing, help, saved results, status display, character handling |
| Packaging | Entry points, bundled data, commands outside the source directory |
| Documentation | Required files, local links, and prohibited em dash characters |

POSIX terminal tests use a pseudo-terminal. They skip where that interface is unavailable. Unit tests for state and input remain separate from terminal rendering tests.

The documentation checker does not assess formal ASD-STE100 compliance. It does not validate external URLs or every shell command.

## Build and test artifacts

```sh
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
python scripts/prepare_release.py dist
```

Install the built wheel into a clean virtual environment. Run the smoke script with that environment's Python:

```sh
python3 -m venv /tmp/fast-verify-wheel-test
/tmp/fast-verify-wheel-test/bin/python -m pip install dist/fast_verify_lab-0.1.2-py3-none-any.whl
/tmp/fast-verify-wheel-test/bin/python scripts/smoke_install.py
```

Use a fresh temporary path if the example path already contains work. Use the current version's wheel filename. Windows uses `Scripts\python.exe` inside the environment.

The smoke script changes to an empty directory. It checks the installed module entry point, bundled cases, offline demo, and benchmark output. This catches accidental dependencies on the source checkout.

## Test the release installer

Build the release wheel first. Then run the installer smoke test:

```sh
python scripts/smoke_release_install.py dist/fast_verify_lab-0.1.2-py3-none-any.whl
```

The smoke test serves the wheel and `SHA256SUMS` from a local HTTP server. It changes the release URL in a temporary installer copy.

It checks installation from a saved script and a script piped to `sh`. It runs the installed demo and JSON question command outside the checkout. The commands use mock responses and create no saved question record.

This test needs no Git checkout at the installation destination, model credentials, or paid calls. It verifies the local release flow. A published GitHub download needs a separate check after release publication.

The unit suite also tests installer behavior with a small fixture wheel, temporary virtual environments, and pip. See the test output for passed and skipped cases.

## CI

The [CI workflow](../.github/workflows/ci.yml) runs on Ubuntu, macOS, and Windows. Its Python matrix contains 3.11 through 3.14.

Separate jobs build release files and test a container's offline demo. POSIX jobs also check the shell installation paths. No CI job requires a model account.

Inspect the [run for your commit](https://github.com/chaeyn/fast-verify-lab/actions/workflows/ci.yml). Report failed or skipped checks separately. Do not describe a configured job as a passing test.

## Manual terminal check

1. Run `fast-verify tui --provider mock`.
2. Press Enter to run a sample.
3. Confirm that the draft appears before review finishes.
4. Open help with F1.
5. Resize the terminal.
6. Scroll the result.
7. Start another run.
8. Cancel it with `x`.
9. Quit with `q`.

Check a narrow window and a window of at least 80 columns. Check Korean text and multiline input when changing text layout.

For a configured provider, confirm that an accepted answer appears once. Confirm that the app still displays its accepted status.

## Optional live check

Live calls can consume usage. Use your own account and a small prompt.

```sh
fast-verify doctor
fast-verify ask "What is 17 times 19? Return only the number." --no-save
```

Record the app version, OS, Python version, CLI version, requested models, result status, and visible answer. Never record keys or raw login files.

Repeat the check for each provider you claim to support live. A successful Codex call does not validate Claude Code or an API adapter.

## Release evidence

Release notes record fresh test results and remaining limits. Historical files in `examples/` describe earlier experiments. Use them as context, not as proof that a new release passed.

Mock accuracy checks pipeline behavior. They cannot establish the accuracy, latency, or cost of a live model.
