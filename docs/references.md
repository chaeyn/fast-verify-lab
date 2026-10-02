# Project references

The public project layout draws on established Python projects. These sources informed documentation and release organization. Fast Verify Lab does not depend on their code.

## Open-source examples

### LLM

Simon Willison's [LLM](https://github.com/simonw/llm) provides a command-line interface for models. Its README links installation, provider setup, usage, and detailed documentation.

For this project, the useful pattern is a short first command followed by focused guides. The installed command, provider table, and separate configuration guide follow that pattern.

### Rich

[Rich](https://github.com/Textualize/rich) provides terminal formatting for Python. Its repository includes compatibility guidance, translated introductions, contribution instructions, and security information.

For this project, the useful pattern is an English entry point with linked translations and explicit environment information. The Korean introduction and contributor documents use that organization.

These references do not imply endorsement. No source code or prose from these projects was copied for this documentation update.

## Technical references

| Source | Use in this project |
|---|---|
| [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) | Simplified writing principles; see the project's [writing rules](writing-style.md) |
| [Codex CLI](https://developers.openai.com/codex/cli/) | Installation and native command behavior |
| [Codex authentication](https://developers.openai.com/codex/auth/) | Saved ChatGPT login |
| [Codex App Server](https://developers.openai.com/codex/app-server/) | Process reuse, requests, and notifications |
| [Claude Code setup](https://code.claude.com/docs/en/setup) | CLI installation and login |
| [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) | Non-interactive command flags |
| [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) | OpenAI HTTP adapter |
| [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create) | Anthropic HTTP adapter |

Project-layout references were reviewed on 2026-10-02. ASD-STE100 Issue 9 is dated 2025-01-15. Provider links can change after a release.

Use the installed CLI help and official provider documentation when behavior differs from an old example. Record versions in bug reports and published experiments.
