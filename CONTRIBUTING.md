# Contributing

You can contribute a bug report, test, provider fix, translation, or documentation change. Read the [code of conduct](CODE_OF_CONDUCT.md) before you participate.

## Choose a change

Check [open issues](https://github.com/chaeyn/fast-verify-lab/issues) for related work. For a large feature, open an issue that describes the user problem and proposed behavior.

Keep each pull request focused on one change. A small documentation correction does not need a separate issue.

## Set up a development environment

Use Python 3.11 or later. Work from the repository root.

```sh
git clone https://github.com/chaeyn/fast-verify-lab.git
cd fast-verify-lab
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[tui]'
python -m pip install build
python -m unittest discover -s tests -v
```

On Windows, create the environment with `py -3 -m venv .venv`. Use `.\.venv\Scripts\python.exe` for the Python commands. Install the `tui` extra to run terminal tests.

Tests use fixed responses, temporary files, local HTTP servers, and CLI stubs. They need no model accounts. Some terminal tests require a POSIX pseudo-terminal and skip on Windows.

## Change code

1. Create a branch for your change.
2. Reproduce the problem with a focused test when behavior changes.
3. Make the smallest change that fixes the problem.
4. Run the relevant tests.
5. Run the full test suite.
6. Update the guide when commands or behavior change.

Use Python's standard library for runtime code where practical. Explain a new runtime dependency in the pull request.

Keep provider errors separate from model verdicts. A timeout, invalid review, or incomplete response must not become an accepted answer.

Do not send bundled expected answers to live models. Keep credentials out of configuration, logs, errors, and test fixtures.

Use the platform helpers for process cancellation. Avoid POSIX-only calls in shared code. Open text files with UTF-8 when their contents can include non-ASCII text.

See [architecture](docs/architecture.md) for components and [testing](docs/testing.md) for validation steps.

## Add or change a provider

A provider must return answer text and available usage from `generate`. It must report incomplete output as a failure.

Add tests for these behaviors:

- The adapter sends the correct model, prompt, and authentication format.
- Each role uses the selected connection.
- The review receives candidate answers but no expected answer.
- Invalid JSON, tool output, and truncated responses fail safely.
- Cancellation stops local CLI processes and allows later runs.
- Errors do not expose provider response bodies or credentials.
- Missing usage remains unknown instead of becoming zero cost.

If the adapter streams drafts, test event order and cancellation after a partial draft. Keep live tests optional. Document the tested provider version and unresolved limits.

## Change documentation

English is the default language. Update [README.ko.md](README.ko.md) when the introduction, installation, or main workflow changes.

Use the project [writing rules](docs/writing-style.md). Keep command names, config keys, and status values unchanged across languages.

Verify each command that you add. Describe the environment and result. Distinguish a local test from a CI test and a live provider call.

Do not put API keys, private prompts, account identifiers, or machine-specific paths in examples. Use relative paths or documented placeholders.

## Open a pull request

Include the following information:

- The user problem and resulting behavior.
- A related issue, if one exists.
- Tests and commands that you ran.
- Platform or provider checks that you could not run.
- Documentation changes, if required.

Use the pull request template. Wait for CI results before requesting a review. The maintainer reviews scope, behavior, tests, and documentation before merging.

The project has no contributor license agreement. Submit only work that you can license under the [MIT license](LICENSE).

## Report a bug

Use the [issue form](https://github.com/chaeyn/fast-verify-lab/issues/new/choose). Include the app version, Python version, operating system, terminal, and command. Add the smallest prompt that reproduces the problem, if you can share it.

Describe the expected result and actual result. Remove credentials and private text before attaching a result file.

For security issues, use [private reporting](SECURITY.md). Do not post a working exploit or exposed key in a public issue.

## Release process

The maintainer prepares a versioned GitHub release. The project does not require PyPI publication.

1. Update the version and [change log](CHANGELOG.md).
2. Run the test and artifact checks in [testing](docs/testing.md).
3. Wait for required CI jobs on the release commit.
4. Build the wheel and source archive from that commit.
5. Create a tag that matches the package version.
6. Attach the artifacts and checksums to the GitHub release.
7. Record test coverage and remaining provider limits in the release notes.

A release tag identifies the code. A green CI run identifies the checks that passed for that code. Neither proves model accuracy or access to an external account.
