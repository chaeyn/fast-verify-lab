# Results and evaluation

[User guide](../GUIDE.md)

## Read the status

| Status | Meaning |
|---|---|
| `accepted` | The reviewer kept the exact draft text |
| `corrected` | The reviewer returned different answer text |
| `uncertain` | The reviewer could not resolve a material claim |
| `verification_failed` | The app received a draft, then verification failed |
| `failed` | The run failed before a draft was available |
| `unreviewed` | A single-model mode returned an answer without review |
| `cancelled` | The user cancelled the run |

Accepted means unchanged by the reviewer. It does not mean externally verified. Corrected means changed by the reviewer. A correction can still be wrong.

The app rejects an accepted review that changes the draft. It also rejects a corrected review that leaves the draft unchanged. Invalid JSON, missing fields, and incomplete responses cause failure.

After a failed or cancelled review, a visible draft remains unverified. Consumers must inspect the status before using the answer.

## Read events

| Event | Contents |
|---|---|
| `draft_delta` | A streamed draft fragment, when supported |
| `draft` | The completed draft |
| `verified` | An accepted status without a repeated answer |
| `final` | A correction, uncertain result, or strong-only answer |
| `error` | A failure status and available draft |

`fast-verify ask --json` emits JSON Lines. Process each line as a separate JSON object. A draft event can precede a verification failure.

## Read timing and usage

`first_token_ms` measures the first streamed draft fragment. `first_answer_ms` measures the completed draft. `final_ms` measures the completed pipeline. Do not compare these fields as if they measure the same event.

Call records include available token usage and duration. Codex App Server can also report process startup, thread startup, and turn duration.

`requested_model` and requested tier describe the request. `session_model` and session tier describe the App Server session. They do not prove the backend's actual model or tier.

A provider can omit usage, cost, model, or tier. `null` means unknown. It does not mean free or zero usage.

## Run a benchmark

```sh
fast-verify bench --provider mock --repeats 3 --seed 42
fast-verify bench --provider configured --repeats 1 --seed 42
```

The second command uses real providers and can incur charges. Each repeat runs each case in all four modes. The bundled six cases require 42 model calls per repeat across those modes.

The app shuffles run order with the seed. It runs cases in sequence. Parallel mode starts its draft and independent answer together.

Each benchmark creates a separate result directory:

| File | Contents |
|---|---|
| `manifest.json` | Provider, config, seed, repeats, and cases |
| `runs.jsonl` | Answers, events, timing, usage, and grades for each run |
| `summary.json` | Accuracy, failures, uncertainty, latency, and known cost |

The expected answer stays in the evaluation stage. Live models receive the question and candidate answers only.

## Add a case

Store one JSON object per line. Use a unique ID and an explicit output format.

```json
{"id":"multiply-small","question":"What is 12 * 13? Return only the integer.","expected":"156"}
```

Run your cases with a real provider:

```sh
fast-verify bench --provider configured --cases cases.jsonl --repeats 1
```

Mock runs also need the fixture fields used in the [bundled dataset](../data/cases.jsonl). Copy a bundled case when testing mock behavior.

The current grader compares text after trimming outer whitespace. It does not judge explanations, execute code, or check sources. Use a task-specific evaluator for those outputs.

## Publish a comparison

Record the commit, dataset, model settings, CLI versions, repeat count, seed, and test environment. Use the same inputs and output constraints for each comparison.

Report failures and regressions with accuracy. A regression occurs when review changes a correct draft into an incorrect answer.

Separate mock results from real calls. Separate first-fragment latency from full-answer latency. Report unknown costs as unknown.

Small samples can show a behavior without establishing a general speed or accuracy advantage. Network, caching, model availability, and account limits can affect each run.

## Archived experiments

The [examples directory](../examples/) contains historical experiment records. Some reports use Korean and earlier command names. They are snapshots of their recorded versions.

The [speed report](../examples/speed-report.md) compares earlier Codex exec and App Server runs. The [initial report](../examples/codex-report.md) documents early model comparisons. Neither is a current release acceptance test.
