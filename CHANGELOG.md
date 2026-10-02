# Change log

## 0.1.1 - 2026-10-02

- Add `sh install.sh` to create or reuse a local virtual environment.
- Add `sh run.sh` to install the app when needed and launch the TUI or a CLI command.
- Preserve command arguments, the working directory, and JSON output through the launcher.
- Include both scripts in the source archive.
- Test shell behavior and real installation on macOS and Linux in CI.

## 0.1.0 - 2026-10-02

First packaged GitHub release.

### Added

- Installable `fast-verify` command and `python -m fast_verify_lab` entry point.
- Setup, diagnostics, text questions, TUI, offline demo, and benchmark commands.
- Per-role connections for Codex, Claude Code, OpenAI, Anthropic, and compatible APIs.
- Platform-specific config and result paths.
- Optional Windows curses dependency and platform-aware process handling.
- CI checks for supported Python versions, package installation, and documentation links.
- English user and contributor documentation, with a Korean introduction.
- MIT license, contribution guidance, and private security reporting instructions.

### Preserved

- Fast draft followed by one review as the default workflow.
- Accepted reviews update the status without repeating the answer.
- Optional independent answer in parallel experiment mode.
- Codex App Server reuse and draft streaming on supported systems.
- Local result records, review failure states, and mock regression cases.

### Limits

- Model reviews can contain errors.
- Live provider access depends on the user's account and installed CLI version.
- Mock, stub, and CI tests do not measure live model accuracy.
- The initial API and Claude adapters display completed responses.

The [support table](docs/support.md) and release notes state the verification scope.
