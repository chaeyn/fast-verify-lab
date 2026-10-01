# User guide

Fast Verify Lab shows a draft first, then asks a second model to review it. If the reviewer accepts the draft, the screen marks the review complete without repeating the answer. If it changes the answer, the screen shows the correction.

## Start in two minutes

Use Python **3.11 or later** on macOS, Linux, or WSL in an interactive terminal. No pip dependencies are required. Native Windows terminals are not supported by this curses UI.

Open a terminal in the repository directory:

```sh
python3 tui.py --provider mock
```

Press Enter to try a sample. Press `q` to quit. Mock responses include intentional mistakes to demonstrate corrections; they do not call a model.

For your own questions:

```sh
python3 tui.py
```

On first launch, the setup wizard asks you to select a **Draft** connection and a **Review** connection and enter their model IDs. It saves `config.local.json`, which Git ignores. Choose models your account can access. The Codex defaults preserve this experiment's draft and review models; they are not guaranteed to exist on another account. Claude Code aliases resolve according to that CLI and account.

After setup, type a question and press Enter. Subsequent launches reuse your configuration. To configure again, press Esc to leave the prompt editor, then `s`, or run:

```sh
python3 setup.py
python3 setup.py --doctor
```

Doctor checks CLI installation, login status and whether the required environment variable exists. It does not make an inference request or prove that a model is available.

## Choose your connection

| Connection | Setup | Transport |
|---|---|---|
| Codex | Install Codex CLI, then `codex login` | ChatGPT login through a persistent Codex App Server |
| Claude Code | Install Claude Code, then `claude auth login` | CLI-managed login through `claude -p` |
| OpenAI API | Set `OPENAI_API_KEY` | Responses API |
| Claude API | Set `ANTHROPIC_API_KEY` | Anthropic Messages API |
| Compatible API | Set the environment variable named in setup | OpenAI-style Chat Completions API |

The two connections can differ. For example, choose Codex for Draft and Claude Code for Review, or a compatible API for Draft and Claude API for Review. Models receive the question; the reviewer also receives the draft. They do not receive the sample's gold answer.

CLI login billing and API billing are separate. API keys use the account behind that key. Claude Code can have subscription or Console login; use `claude auth status` to inspect your login. This program removes API key and provider override environment variables from Claude Code calls and uses its saved login. It does not extract OAuth tokens. Codex requires a ChatGPT login. Account limits and model availability remain provider-specific.

### Codex

Follow the [official installation and authentication instructions](https://learn.chatgpt.com/docs/auth), then:

```sh
codex login
codex login status
python3 tui.py --provider codex
```

`config.codex.json` contains the existing experiment's models and reasoning levels. Use setup to choose other models. The default App Server path requires a file-based native login. If your login lives only in a keyring, set `"transport": "exec"` in the configuration. App Server keeps the process warm, streams the draft and creates a new ephemeral model thread for each call.

### Claude Code

Install the CLI with the [official setup guide](https://code.claude.com/docs/en/setup), then:

```sh
claude auth login
claude auth status
python3 tui.py --provider claude
```

`config.claude.json` uses the `haiku` and `sonnet` aliases. You can specify full IDs through setup or a custom config. The adapter uses `--safe-mode`, disables built-in tools and MCP, runs from an empty temporary directory, and disables session persistence. Managed organization policies still apply. The installed CLI must support these flags; see the [CLI reference](https://code.claude.com/docs/en/cli-reference).

Claude Code starts a separate CLI process per call. This version displays the completed Claude response rather than streaming it, so its first-visible latency can differ from Codex App Server.

### API keys

Set the key in the **same terminal** that launches the UI. Avoid putting keys into JSON, screenshots or shared shell scripts. The program does not load `.env` automatically. For zsh, read the key without displaying it:

```sh
read -rs 'OPENAI_API_KEY?OpenAI API key: '; echo
export OPENAI_API_KEY
# Or, for Claude API:
read -rs 'ANTHROPIC_API_KEY?Claude API key: '; echo
export ANTHROPIC_API_KEY
python3 setup.py
python3 tui.py
```

For bash, use `read -rsp 'API key: ' OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`), then export the variable. Setup asks for the **variable name**, never the key itself. For two compatible endpoints using different keys, give each role a different variable name.

Enter actual API model IDs during setup. API example files contain placeholders rather than guessing which models your account can use. OpenAI supports an optional `reasoning_effort`; leave it empty if the model does not support it. Claude API uses the model's default reasoning behavior in this adapter.

The compatible adapter requires `/chat/completions`. An endpoint that only implements `/responses` needs the OpenAI adapter instead. Include the API version path in `base_url` (for example, `https://your-host/v1`). Compatible servers differ in supported models and parameters. `json_mode: true` enables JSON mode for review when the server supports it. Without it, the reviewer still receives JSON instructions and the application validates its output.

Current HTTP adapters show completed responses, use a per-call timeout and do not retry automatically. Cancelling the UI task may leave an HTTP request running until its timeout. API or CLI operations may still consume usage after cancellation. CLI cancellation kills Claude/exec processes or interrupts Codex App Server turns.

API references: [OpenAI text generation](https://developers.openai.com/api/docs/guides/text), [Claude Messages](https://platform.claude.com/docs/en/api/messages/create).

## Keyboard and workflow

| Key | Action |
|---|---|
| Enter | Run the prompt or selected sample |
| Ctrl+O | Insert a newline while editing |
| Ctrl+D | Run a multiline prompt |
| Ctrl+W / Ctrl+U | Delete the last word / clear the prompt |
| Esc | Leave prompt editing |
| n / e | New prompt / edit the current question |
| s | Configure the two connections outside the editor |
| F1 | Open help from any screen |
| ? | Open help outside the editor |
| PgUp / PgDn | Scroll the answer or help |
| x | Cancel the active run |
| q | Quit outside the editor |
| ↑ / ↓ / r | Select / return to sample cases |
| m / p | Cycle experiment modes / single-provider presets |

Use `sequential` for draft → one review. `fast` and `strong` call one model without review. `parallel` adds an independent answer and uses three calls; it is an experiment option and can take longer.

Provider presets use their default config file unless you pass `--config`. Use `s` for mixed connections and custom models. `--provider configured` selects the saved two-connection config. If you pass a custom config with a single provider, also pass that provider explicitly.

`accepted` means the reviewer kept the draft. It does not prove factual correctness. `corrected` means it changed the answer. `uncertain` means it could not resolve a claim. A failed review leaves the draft visible and unverified. Use `e` to adjust your question or Enter to retry.

## Saved results

By default, the UI saves the question, answers, status, events and available usage to `results/ui-*.json`. Each question starts a fresh model conversation. The result file is a run record, not conversational memory for the next question.

To avoid local result files:

```sh
python3 tui.py --no-save
```

This option does not change the provider's retention policy or erase previous files. Configuration and result files stay local unless you share them. Do not commit files containing credentials or private questions. Estimated costs may be unavailable; the adapters do not claim to measure your bill.

## Troubleshooting

| Symptom | Action |
|---|---|
| TUI requires an interactive terminal | Run the command in Terminal, not a pipe or output-only panel |
| Missing CLI or login | Run setup doctor; install and sign in to the selected CLI |
| Missing environment variable | Export the key in the terminal launching the UI |
| HTTP 401 / 403 | Check key validity, account access and endpoint |
| HTTP 404 / 400 | Check model ID, base URL and supported reasoning options |
| HTTP 429 | Check provider usage limits, then retry later |
| Review failed | Check login/model access and JSON support; the draft remains unverified |
| Terminal too small | Resize to at least 40 columns × 12 rows; larger windows show the ASCII banner |
| Codex file-based login unavailable | Use `transport: exec` in your Codex config |

Run the local transport and UI tests:

```sh
python3 -m unittest discover -s tests -v
```

Tests use local HTTP servers and CLI stubs. They verify routing, request formats, cancellation, failed reviews and terminal behavior. They do not prove live Claude/API access. Use a small real prompt after checking your account setup.
