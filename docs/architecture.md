# Architecture

[Contributing](../CONTRIBUTING.md)

## Components

| File | Responsibility |
|---|---|
| `cli.py` | Installed command parsing and text question workflow |
| `configure.py` | Setup wizard and local diagnostics |
| `tui.py` | Keyboard input, screen rendering, and a background run worker |
| `lab.py` | Pipeline, review validation, benchmark grading, and core providers |
| `providers.py` | Per-role routing, HTTP adapters, and Claude Code adapter |
| `codex_server.py` | Persistent Codex App Server transport |
| `paths.py` | Config, resource, and result locations |
| `process_utils.py` | Platform-aware subprocess creation and cancellation |
| `data/cases.jsonl` | Offline samples and exact expected answers |

The package installs these modules as `fast_verify_lab`. The source commands remain available for development. Use the installed `fast-verify` command in user documentation.

## Pipeline

The `fast` role produces the draft. The `strong` role performs the review. Role names describe their purpose; users select the actual models.

In sequential mode, the pipeline emits the draft before it starts the review. In parallel mode, it starts the draft and an independent answer together. Review starts after both answers arrive.

The reviewer receives the question, draft, and optional independent answer. It returns JSON with `status`, `answer`, and `reason`.

`parse_review` checks the field types and status. An accepted answer must equal the draft. A corrected answer must differ from the draft. The pipeline emits `verified` for acceptance and `final` for a correction or uncertainty.

A provider error after a draft produces `verification_failed`. The app retains the draft and failure status. It does not replace a failure with acceptance.

## Provider boundary

Each provider exposes an asynchronous `generate` method. It returns text, duration, and available metadata. Providers that support draft streaming also accept an event callback.

`RoleProvider` creates clients when required. It combines common settings with per-role connection settings. It reuses a client only when provider and connection settings match.

HTTP calls run through Python's standard HTTP library in worker threads. Cancellation can leave a network operation active until its timeout. CLI calls use platform-aware subprocess cleanup.

The app does not retry automatically. Retries would change measured latency and could repeat billed requests.

## Codex App Server

The transport owns a background event loop. The TUI can submit calls from separate workers while one App Server process remains open.

JSON-RPC requests use request IDs. Notifications route to the active ephemeral thread. Each model call creates a fresh thread. The transport interrupts a cancelled turn and closes all resources on shutdown.

A temporary config directory isolates the experiment from user project instructions and tools. A credential-file link lets the native CLI manage login. Native Windows and keyring-only configurations use exec through the provider factory.

## Persistence

Config files contain connection settings and environment variable names. API keys remain in environment variables. Result files can contain the full question and answer.

A benchmark writes its manifest before runs. It appends each result to JSON Lines and produces a summary. The expected answer enters grading only.

User state lives outside the installed package. A local `config.local.json` remains available for source checkout workflows. See [configuration](configuration.md) for precedence.

## UI boundary

The TUI handles events on its main thread. A worker runs asynchronous model calls and sends events through a queue. The screen removes control characters and wraps text to fit the terminal.

The text CLI provides an alternative for pipes, headless environments, and users who do not use curses. Both interfaces use the same pipeline and status semantics.
