# Fast Verify Lab

[한국어 소개](README.ko.md) · [User guide](GUIDE.md) · [Contributing](CONTRIBUTING.md) · [Releases](https://github.com/chaeyn/fast-verify-lab/releases)

Show a fast model's answer. Ask a second model to review it. Keep the answer when the reviewer accepts it. Show a correction when the reviewer changes it.

Fast Verify Lab is a terminal application and a model comparison tool. Choose separate providers and models for the draft and review.

```text
Question -> Fast draft -> Review -> Accepted: keep the draft
                                -> Corrected: show the correction
                                -> Uncertain or failed: show the review status
```

A review is a model judgment. Both models can make the same mistake. An `accepted` status does not prove that an answer is correct.

## Try it

Use Python 3.11 or later. The mock demo needs no account, API key, or external model.

### macOS, Linux, or WSL

```sh
git clone https://github.com/chaeyn/fast-verify-lab.git
cd fast-verify-lab
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[tui]'
fast-verify demo
fast-verify tui --provider mock
```

### Windows PowerShell

```powershell
git clone https://github.com/chaeyn/fast-verify-lab.git
cd fast-verify-lab
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[tui]"
.\.venv\Scripts\fast-verify.exe demo
.\.venv\Scripts\fast-verify.exe tui --provider mock
```

The `tui` extra installs `windows-curses` on Windows. The text CLI has no runtime package dependencies. See the [environment support table](docs/support.md) for test limits.

## Connect a model

1. Install the CLI or obtain an API key for your provider.
2. Run `fast-verify setup`.
3. Select a Draft connection and a Review connection.
4. Enter model IDs that your account can use.
5. Run `fast-verify doctor`.
6. Run `fast-verify tui`.

On Windows, use `.\.venv\Scripts\fast-verify.exe` in place of `fast-verify` if the virtual environment is not active.

| Connection | Authentication | Provider ID |
|---|---|---|
| Codex | Saved ChatGPT login from Codex CLI | `codex` |
| Claude Code | Saved login from Claude Code CLI | `claude` |
| OpenAI API | `OPENAI_API_KEY` | `openai` |
| Anthropic API | `ANTHROPIC_API_KEY` | `anthropic` |
| OpenAI-compatible API | An environment variable that you select | `api` |
| Offline examples | No authentication | `mock` |

The default mode makes two calls: one draft and one review. API calls can incur charges. CLI calls use the account managed by each CLI. The [user guide](GUIDE.md) explains login, keys, mixed providers, and cancellation.

## Use the text CLI

```sh
fast-verify ask "What is 17 times 19? Return only the number."
fast-verify ask "Explain a binary search in three sentences." --no-save
fast-verify ask "Check this calculation: 23 * 11 = 253." --json
fast-verify bench --provider mock --repeats 3
```

`ask` uses your saved configuration. `demo` and `bench` use mock responses unless you select another provider. Mock responses include deliberate errors. Their scores do not measure model quality.

The app saves prompts and answers by default. Use `--no-save` with `ask` or `tui` to stop local result creation. Provider retention policies still apply.

## Find help

| Task | Read |
|---|---|
| Install, sign in, use the TUI, or fix an error | [User guide](GUIDE.md) |
| Set models, paths, timeouts, or API endpoints | [Configuration](docs/configuration.md) |
| Read review status and benchmark results | [Results and evaluation](docs/results.md) |
| Check platforms and provider test coverage | [Support](docs/support.md) |
| Change code or documentation | [Contributing](CONTRIBUTING.md) |
| Understand components and data flow | [Architecture](docs/architecture.md) |
| Reproduce tests | [Testing](docs/testing.md) |
| Report a security issue | [Security policy](SECURITY.md) |

English is the default documentation and interface language. The [Korean introduction](README.ko.md) covers installation and the main workflow. Prompts and answers keep their requested language.

## Project scope

This project supports text questions, model review, terminal output, and repeatable experiments. It does not perform web research or execute model-generated actions. Each question starts a fresh model conversation.

The API adapters use Python's standard library. Codex and Claude Code run as separate installed applications. Provider versions and account access can change behavior.

This project uses the [MIT license](LICENSE). See the [change log](CHANGELOG.md) for releases and [project references](docs/references.md) for documentation influences.
