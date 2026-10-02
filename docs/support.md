# Support and compatibility

[User guide](../GUIDE.md)

Use Python 3.11 or later. The CI matrix covers Python 3.11, 3.12, 3.13, and 3.14. A newer Python version can work without being in this matrix.

## Environments

| Environment | Implementation | Automated coverage | Limits |
|---|---|---|---|
| macOS | Text CLI and curses TUI | Unit tests, POSIX terminal tests, install smoke in CI | Live provider access needs a local account |
| Linux | Text CLI and curses TUI | Unit tests, POSIX terminal tests, install smoke in CI | Some Python distributions require a separate curses package |
| Windows | Text CLI; TUI with `windows-curses` | Unit tests and install smoke in CI | POSIX pseudo-terminal tests skip; manual terminal appearance needs a Windows check |
| WSL | Linux execution path | Covered by Linux code paths; no dedicated WSL job | Install Python and provider CLIs inside WSL |
| Container | Text CLI and HTTP providers | Image build and offline demo smoke in CI | CLI login and interactive TUI are not container acceptance tests |
| SSH or headless shell | Text CLI | Installed CLI smoke uses a non-interactive process | TUI needs a working interactive terminal |

“Coverage” describes the configured checks. See the [CI runs](https://github.com/chaeyn/fast-verify-lab/actions/workflows/ci.yml) for the result on a specific commit. A workflow file alone is not evidence that its checks passed.

Native Windows uses the Codex exec transport. POSIX systems can reuse a Codex App Server process when file-based login is available.

## Provider coverage

| Provider | Offline verification | Live evidence |
|---|---|---|
| Mock | Fixed cases, review states, failure and regression tests | No external service |
| Codex App Server | RPC stub, streaming, reuse, disconnect, and cancellation tests | Historical local calls in [examples](../examples/); see release notes for fresh checks |
| Codex exec | CLI stub, response parsing, failure, and cancellation tests | Historical local calls in [examples](../examples/) |
| Claude Code | Command construction, isolation, parsing, and cancellation tests | No authenticated live call claimed for this release |
| OpenAI Responses | Local HTTP request and response tests | No authenticated live call claimed for this release |
| Anthropic Messages | Local HTTP request and response tests | No authenticated live call claimed for this release |
| Compatible API | Local HTTP request and response tests | External endpoint compatibility needs an account-specific check |

CI uses local fixtures and stubs. It does not use model keys or paid provider accounts. A passing transport test does not prove current model availability.

## Supported use

The app accepts text questions and supplied evidence. It displays a draft, records a review, and can compare fixed test cases.

The app does not fetch current sources, browse websites, or run generated code. A reviewer can repeat a draft's error. Use external sources or a task-specific evaluator when accuracy requires them.

The TUI labels are English. The Korean introduction covers the main workflow. Models can answer in Korean or another requested language.

## Version changes

Provider CLIs and APIs can change. Record `codex --version` or `claude --version` when reporting an adapter failure.

Use `fast-verify --version` for the app version. Include the installed package version and commit when reporting a source checkout issue.

See [release notes](https://github.com/chaeyn/fast-verify-lab/releases) for tested versions and unresolved limits.
