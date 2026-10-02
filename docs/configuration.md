# Configuration

[User guide](../GUIDE.md)

Use `fast-verify setup` to create a config. Use `fast-verify doctor` to check local settings. Both commands accept `--config PATH`.

## File locations

The app chooses a config in this order:

1. The path in `--config`.
2. The path in `FAST_VERIFY_CONFIG`.
3. `config.local.json` in the current directory, if it exists.
4. The user config shown below.

| System | Default config | Default results |
|---|---|---|
| macOS | `~/Library/Application Support/fast-verify-lab/config.json` | `~/Library/Application Support/fast-verify-lab/results/` |
| Linux and WSL | `~/.config/fast-verify-lab/config.json` | `~/.local/state/fast-verify-lab/results/` |
| Windows | `%APPDATA%/fast-verify-lab/config.json` | `%LOCALAPPDATA%/fast-verify-lab/results/` |

Linux respects `XDG_CONFIG_HOME` for config and `XDG_STATE_HOME` for results. Results use `--output`, then `FAST_VERIFY_RESULTS_DIR`, then the platform default.

A preset such as `--provider codex` selects its bundled config unless you also pass `--config`. Use `--provider configured` for per-role provider settings. For a legacy config without role providers, also specify its provider, such as `--provider codex --config PATH`.

Config and result directories are separate from the installed package. Reinstalling the app does not reset these files.

## Example: mixed connections

This example uses Codex for the draft and Anthropic API for the review. Replace the model placeholders with IDs that your account can use.

```json
{
  "timeout_seconds": 120,
  "max_output_tokens": 4096,
  "fast": {
    "provider": "codex",
    "model": "YOUR_CODEX_MODEL",
    "reasoning_effort": "low",
    "transport": "app-server"
  },
  "strong": {
    "provider": "anthropic",
    "model": "YOUR_ANTHROPIC_MODEL",
    "base_url": "https://api.anthropic.com/v1",
    "api_key_env": "ANTHROPIC_API_KEY"
  }
}
```

Save the file as `config.local.json`. Set the key in your terminal. Then run:

```sh
fast-verify doctor --config config.local.json
fast-verify ask "What is 17 times 19?" --config config.local.json --no-save
```

The config key `fast` means Draft. The key `strong` means Review. In strong-only mode, `strong` answers the question directly.

## Settings

| Setting | Location | Meaning |
|---|---|---|
| `provider` | Each role | `codex`, `claude`, `openai`, `anthropic`, or `api` |
| `model` | Each role | Model ID or CLI model alias |
| `reasoning_effort` | Each role | Optional effort for Codex, Claude Code, or OpenAI |
| `service_tier` | Codex role | Requested tier, if the account supports it |
| `base_url` | Common or role | API root, including a required version path |
| `api_key_env` | Common or role | Environment variable name for a key |
| `transport` | Common or Codex role | `app-server` or `exec` |
| `timeout_seconds` | Common or role | Maximum time for each call |
| `max_output_tokens` | Common or role | Output limit for HTTP adapters |
| `json_mode` | Common or compatible API role | Enable JSON mode for review |

Per-role connection settings override common settings. Two roles can use the same provider with different endpoints and key variables.

Reasoning values depend on the model and CLI. Omit `reasoning_effort` to use the provider default. The Anthropic HTTP adapter uses its default reasoning behavior.

`max_output_tokens` does not set a token limit for Codex or Claude Code. These CLIs apply their own limits.

## Codex transport

On POSIX systems with a file-based login, the default path uses a persistent App Server. On native Windows, the factory selects exec. It also selects exec when `auth.json` is absent.

If the filesystem rejects the credential link, set `transport` to `exec`. Exec uses the native CLI login and displays the completed answer. App Server streams the draft.

The bundled Codex preset retains the initial experiment's model IDs. They are examples, not account-independent defaults. Use setup to select accessible models.

## Compatible APIs

The `api` provider sends requests to `base_url` plus `/chat/completions`. The endpoint must return a text message and a completed finish reason.

A service that only supports `/responses` needs the `openai` provider. That adapter uses the Responses request and response format.

JSON mode is optional for compatible APIs. A server can reject unsupported request fields. Keep `json_mode` off until you confirm support.

## Estimated cost

The OpenAI adapter can estimate USD cost from returned usage and these per-role rates:

- `input_usd_per_million`
- `cached_input_usd_per_million`
- `output_usd_per_million`

Set all three rates to use the estimate. Missing usage or rates produce `null`. CLI subscription usage and other adapters do not provide a bill estimate.

The estimate can differ from your invoice. Record the source and date of rates when you publish a comparison.

## Environment variables

| Variable | Purpose |
|---|---|
| `FAST_VERIFY_CONFIG` | Default custom config path |
| `FAST_VERIFY_RESULTS_DIR` | Default result directory |
| `OPENAI_API_KEY` | Default OpenAI and compatible API key |
| `ANTHROPIC_API_KEY` | Default Anthropic API key |
| A custom `api_key_env` name | Key for a specific connection |

The app does not load `.env` files. CLI adapters use their native saved login and remove API overrides from child processes. See the [security policy](../SECURITY.md) before sharing config or result files.
