# Security policy

## Supported versions

The maintainer accepts security reports for the latest release and the current `main` branch. Upgrade to the latest release before checking whether a fix applies.

This is a small volunteer project. Response time depends on maintainer availability.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/chaeyn/fast-verify-lab/security/advisories/new).

Include the affected version, operating system, reproduction steps, and expected impact. Use dummy credentials and a minimal prompt. Do not include active keys or private account data.

If private reporting is unavailable, use a private contact method listed on the [maintainer profile](https://github.com/chaeyn). Do not post vulnerability details publicly while you arrange private contact.

If a key is exposed, revoke it through its provider. Removing a file or Git commit does not revoke the key.

## Data flow

The selected provider receives your question. A review provider also receives the draft. In parallel mode, it receives the independent answer as well.

The app stores prompts and answers in local result files by default. Use `--no-save` with `ask` or `tui` to stop local result creation. Provider storage and terminal history are separate.

API keys come from environment variables. Config files contain key variable names. The app does not load `.env` automatically.

Codex and Claude Code manage their own login credentials. The app invokes those CLIs. Codex App Server can use a link to the CLI's credential file in a temporary directory.

## Trust limits

Model output is untrusted input. The app validates review structure and status. The TUI removes terminal control characters before display.

The project requests text answers without model tools. It is not a sandbox for arbitrary code or hostile local executables. Install provider CLIs only from sources that you trust.

Use HTTPS for remote API endpoints. Plain HTTP can expose prompts and credentials in transit. Local test servers can use loopback HTTP.

Config validation rejects known credential fields. It cannot identify every secret pasted into a model ID, URL, or prompt. Review files before you share them.
