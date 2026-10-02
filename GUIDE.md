# User guide

[Home](README.md) · [한국어 소개](README.ko.md)

Fast Verify Lab shows a draft before the review finishes. The reviewer can keep the draft, change it, or report uncertainty.

## Install

Use Python 3.11 or later. Follow the [installation steps](README.md#try-it) for your operating system. Run commands inside the virtual environment.

Use `python -m fast_verify_lab` if the `fast-verify` command is not on your PATH. Both commands provide the same interface.

```sh
python -m fast_verify_lab --help
fast-verify --help
```

Install from the GitHub source or a GitHub release artifact. This guide does not require a PyPI publication.

To update a source checkout:

1. Save your local code changes.
2. Pull the version that you want to use.
3. Run `python -m pip install '.[tui]'` again.
4. Run `fast-verify doctor`.

## Use a container

The image supports the text CLI. The image does not include Codex or Claude Code.

From a source checkout:

```sh
docker build --tag fast-verify-lab .
docker run --rm fast-verify-lab demo --provider mock
```

For an API connection, create `config.local.json` with `fast-verify setup --config config.local.json`. Select HTTP providers for both roles. Set their key variables in the host terminal.

This example uses a POSIX shell and an OpenAI key:

```sh
docker run --rm \
  --env OPENAI_API_KEY \
  --volume "$PWD/config.local.json:/config.json:ro" \
  fast-verify-lab ask "What is 17 times 19?" --config /config.json --no-save
```

Pass each key variable needed by the config. The container reads the mounted config and prints the result. `--no-save` avoids a result file inside the disposable container.

## Run without an account

```sh
fast-verify demo
fast-verify tui --provider mock
```

In the TUI, press Enter to run the selected sample. Press `q` to quit. Mock mode uses fixed answers, including deliberate errors. It supports the bundled samples only.

## Configure two connections

```sh
fast-verify setup
fast-verify doctor
fast-verify tui
```

Setup asks for a Draft connection and a Review connection. Each connection has its own provider and model. For example, you can use Codex for Draft and Claude Code for Review.

Enter model IDs that your account can use. Preset model names come from earlier experiments. They can be unavailable to other accounts.

Setup stores model IDs and connection settings. It asks for an environment variable name when a provider needs an API key. It does not ask for the key itself.

Doctor checks local configuration, CLI installation, saved login, and key variable presence. It does not call a model. A successful check does not prove model access or API connectivity.

Use a small question to test your connection:

```sh
fast-verify ask "What is 17 times 19? Return only the number." --no-save
```

This command can consume provider usage. See [configuration](docs/configuration.md) for config paths, endpoint settings, and separate keys for each role.

## Choose a provider

| Provider | Protocol | Draft display |
|---|---|---|
| `codex` | Official Codex App Server, or `codex exec` | Streams with App Server; completed text with exec |
| `claude` | Official Claude Code CLI | Completed text |
| `openai` | OpenAI Responses API | Completed text |
| `anthropic` | Anthropic Messages API | Completed text |
| `api` | OpenAI-compatible Chat Completions API | Completed text |

`configured` routes each role to the provider in your saved config. Use this provider for mixed connections.

CLI login and API keys use separate authentication paths. API charges follow the key's account. CLI usage follows the saved CLI login and its account terms.

### Codex

1. Install Codex with the [official setup instructions](https://developers.openai.com/codex/cli/).
2. Run `codex login`.
3. Run `codex login status`.
4. Select Codex in `fast-verify setup`.

The adapter requires a ChatGPT login. It removes API key environment variables from the child process. It does not extract OAuth tokens.

App Server keeps one process open during a TUI session or benchmark. Each call creates a new ephemeral thread. The next question does not receive the previous question or answer.

App Server uses a temporary configuration directory. It links the CLI's existing file-based credential file. The application does not read or copy token contents. It disables project documents, shell tools, and web search.

The provider factory selects exec on native Windows and when `auth.json` is absent. If a filesystem rejects the App Server credential link, set `transport` to `exec`.

```json
{
  "fast": {"provider": "codex", "model": "YOUR_DRAFT_MODEL", "transport": "exec"},
  "strong": {"provider": "codex", "model": "YOUR_REVIEW_MODEL", "transport": "exec"}
}
```

Use actual model IDs in place of `YOUR_DRAFT_MODEL` and `YOUR_REVIEW_MODEL`. Add the common settings from the [configuration example](docs/configuration.md#example-mixed-connections).

See [Codex authentication](https://developers.openai.com/codex/auth/) and [App Server](https://developers.openai.com/codex/app-server/) for provider behavior.

### Claude Code

1. Install Claude Code with its [official setup guide](https://code.claude.com/docs/en/setup).
2. Run `claude auth login`.
3. Run `claude auth status`.
4. Select Claude Code in `fast-verify setup`.

The adapter uses the CLI's saved login. It removes API key and provider override environment variables from the child process. It starts one CLI process for each call.

The adapter disables built-in tools, MCP servers, hooks, and session persistence. It runs from an empty temporary directory. Managed organization policies still apply.

The installed CLI must support the adapter's flags. Check the [CLI reference](https://code.claude.com/docs/en/cli-reference) if a command fails. The bundled aliases are `haiku` and `sonnet`; their resolved models depend on the CLI and account.

### API keys

Set the key in the terminal that starts Fast Verify Lab. The app does not load `.env` files automatically.

For bash:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY
printf '\n'
export OPENAI_API_KEY
fast-verify setup
```

For zsh:

```zsh
read -rs 'OPENAI_API_KEY?OpenAI API key: '
printf '\n'
export OPENAI_API_KEY
fast-verify setup
```

For PowerShell 7:

```powershell
$env:OPENAI_API_KEY = Read-Host 'OpenAI API key' -MaskInput
.\.venv\Scripts\fast-verify.exe setup
```

For Anthropic API, use `ANTHROPIC_API_KEY` in place of `OPENAI_API_KEY`. For a compatible API, use the variable name saved in your config.

Keep keys out of JSON config, screenshots, and issue reports. The input commands above avoid placing the key in shell history.

OpenAI uses `/responses`. Anthropic uses `/messages`. The compatible adapter uses `/chat/completions`. Include the required version path in `base_url`, such as `https://example.com/v1`.

Compatible endpoints differ. Set `json_mode` to `true` only when the endpoint supports it. The app validates the review JSON even when JSON mode is off.

HTTP adapters use a timeout for each call. They do not retry automatically. A cancelled HTTP request can continue until the timeout and can still consume usage.

Provider references: [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create).

## Use the TUI

Run `fast-verify tui` in an interactive terminal. Use a window of at least 40 columns and 12 rows. A larger window shows the ASCII banner.

Enter a question, then press Enter. The app shows the draft as it becomes available. An accepted review changes the status without repeating the answer.

| Key | Action |
|---|---|
| Enter | Run the prompt or selected sample |
| Ctrl+O | Insert a newline in the prompt |
| Ctrl+D | Run a multiline prompt |
| Ctrl+W | Delete the last word |
| Ctrl+U | Clear the prompt |
| Esc | Leave prompt editing |
| n / e | Start a new prompt / edit the current prompt |
| s | Configure connections outside the editor |
| F1 | Open help |
| ? | Open help outside the editor |
| PgUp / PgDn | Scroll the answer or help |
| x | Cancel the current run |
| q | Quit outside the editor |
| Up / Down | Select a sample |
| r | Return to the sample list |
| m | Change the experiment mode |
| p | Change the single-provider preset |

While a run is active, you can scroll, cancel, or quit. The selected question and connections stay fixed until the run ends.

The TUI uses English labels. Prompts and answers keep the language that you request. Use the text CLI if your terminal cannot render the TUI or you use assistive technology.

## Use the text CLI

```sh
fast-verify ask "What is 17 times 19?"
fast-verify ask "Explain a queue in two sentences." --no-save
fast-verify ask "What is 17 times 19?" --json
```

You can pass a prompt through standard input:

```sh
printf '%s\n' 'What is 17 times 19?' | fast-verify ask --no-save
```

For PowerShell:

```powershell
'What is 17 times 19?' | .\.venv\Scripts\fast-verify.exe ask --no-save
```

Use `--prompt-file PATH` to read a UTF-8 prompt file. Select one prompt source: a positional question, a file, or standard input.

Use `--json` for one JSON event per line. Consume the review status as well as the answer. A draft event can arrive before a later verification failure.

Exit code `0` means the pipeline completed, including an uncertain verdict. Code `1` means a run or review failed. Code `2` means invalid input or configuration. Code `130` means keyboard cancellation.

Use `--config PATH` for a specific config. Use `--provider configured` for config files with per-role providers. For an older single-provider config, pass its provider explicitly, such as `--provider codex --config PATH`.

## Select a mode

| Mode | Calls | Behavior |
|---|---:|---|
| `fast` | 1 | Draft model only; no review |
| `strong` | 1 | Review model answers directly; no review |
| `sequential` | 2 | Draft, then review |
| `parallel` | 3 | Draft and independent answer together, then review |

Use `sequential` for the default workflow. In `parallel`, the independent model does not receive the draft. The final review receives both answers. The extra call can increase total time and usage.

## Save or discard local results

The app saves question text, answers, events, timing, and available token usage. Each result describes one run. It does not create conversational memory for later questions.

```sh
fast-verify tui --no-save
fast-verify ask "What is 17 times 19?" --no-save
```

`--no-save` stops local result creation for that command. It does not remove existing files or change provider retention. Your terminal can still retain displayed output.

`bench` writes experiment files. `demo` prints events. See [result fields](docs/results.md) and [default storage paths](docs/configuration.md#file-locations).

## Fix a problem

| Symptom | Action |
|---|---|
| `fast-verify` is not found | Activate the virtual environment, or use `python -m fast_verify_lab` |
| Python version error | Install Python 3.11 or later and recreate the virtual environment |
| Missing curses on Windows | Install the `tui` extra with the same Python environment |
| TUI requires an interactive terminal | Open a terminal, or use `fast-verify ask` |
| Terminal is too small | Resize to at least 40 columns and 12 rows |
| CLI or login is missing | Run `fast-verify doctor`, then install or sign in to the named CLI |
| Key variable is missing | Set the key in the terminal that starts the app |
| HTTP 401 or 403 | Check the key, account access, and endpoint |
| HTTP 400 or 404 | Check the model ID, endpoint path, and model options |
| HTTP 429 | Check provider limits, then retry later |
| Review fails | Check JSON support and model access; the draft remains unverified |
| Codex credential link fails | Use `transport: exec` and check the CLI login |
| Claude exits before an answer | Check CLI version, supported flags, and saved login |

If the problem continues, use the [bug report form](https://github.com/chaeyn/fast-verify-lab/issues/new/choose). Include the OS, Python version, app version, command, and error type. Remove keys and private prompts.
