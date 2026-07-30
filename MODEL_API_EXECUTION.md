# Model API execution

The formal pipeline supports three interchangeable execution backends. They all
run the same batches and quality gates:

- `api`: remote model API;
- `cli`: an installed Claude Code/Codex-style stdin/stdout agent;
- `custom`: a user-supplied file-based runner.

Do not put API keys in this file, `.env.example`, patient JSON, or Git. Set them
in the shell or CI Secrets.

## OpenAI

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=openai
export MODEL_NAME=gpt-5
export OPENAI_API_KEY='your-key'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir run
```

## Anthropic

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=anthropic
export MODEL_NAME=your-claude-model-id
export ANTHROPIC_API_KEY='your-key'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir run
```

## GLM

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=glm
export MODEL_NAME=your-glm-model-id
export GLM_API_KEY='your-key'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir run
```

## MiniMax

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=minimax
export MODEL_NAME=your-minimax-model-id
export MINIMAX_API_KEY='your-key'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir run
```

Set `MODEL_BASE_URL=https://api.minimaxi.com/v1` for the mainland China MiniMax
endpoint. The preset defaults to the international endpoint.

## Any OpenAI-compatible provider

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=openai-compatible
export MODEL_BASE_URL=https://provider.example/v1
export MODEL_API_KEY='your-key'
export MODEL_NAME=provider-model-id
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir run
```

This covers a provider only when it implements the OpenAI
`/v1/chat/completions` request and response contract. A model name is passed
through unchanged, so newly released models do not require a code change.

Some compatible endpoints reject optional fields. JSON mode is therefore
opt-in (`MODEL_ENABLE_JSON_MODE=1`), and temperature is sent only when
`MODEL_TEMPERATURE` is set. Use `MODEL_TOKEN_PARAMETER=max_completion_tokens`
when required by the provider.

For local Ollama/vLLM-compatible endpoints only:

```bash
export MODEL_BASE_URL=http://127.0.0.1:11434/v1
export MODEL_ALLOW_INSECURE_HTTP=1
export MODEL_ALLOW_EMPTY_API_KEY=1
```

Remote plain HTTP is rejected because it would expose patient data and the API
key in transit.

## Skill resources

The API runner selects only the subskills listed in the current job's
`required_execution_order`. It embeds each selected `SKILL.md` plus its explicit
relative Markdown/JSON links, including the output schema files. Output schemas
are placed after the job envelope so their field contract remains prominent.

Resources must stay inside their own skill directory. Missing resources,
directory traversal, unsupported file types, excessive link depth, and excessive
file counts fail before any paid API request. Limits are controlled by
`MODEL_SKILL_MAX_FILES` and `MODEL_SKILL_MAX_DEPTH`.

Subskills emit their own native per-trial schemas. The deterministic batch
adapter, not the model, maps those schemas into the internal analysis bundle:

- trial-gater fields become `gating`;
- trial-risk-annotator fields become `risk_annotation`;
- trial-efficacy-contextualizer fields become `efficacy_context`;
- the deep stage reuses the authoritative gater result from its input and does
  not ask the model to reproduce it.

Direct and already nested outputs are both accepted when consistent. Conflicting
direct/nested values are rejected rather than silently choosing one.

## Resume and cost control

The executor validates each output's exact trial-ID set and resumes valid batch
files. Validation covers JSON shape, exact IDs, and the gater/deep stage
contract. Invalid responses are quarantined with an error note. After repeated
whole-batch contract failures, the executor falls back to resumable one-trial
requests and aggregates them only after every item validates. A failed API call
can therefore be retried without rerunning completed batches.

Only one `execute` process may use a run directory at a time. The OS-held lock
is released automatically when the process exits, including abnormal exits.
Control request behavior with:

- `MODEL_API_TIMEOUT_SECONDS`;
- `MODEL_API_RETRIES`;
- `MODEL_API_RETRY_BASE_SECONDS`;
- `MODEL_MAX_INPUT_CHARS`;
- `MODEL_MAX_OUTPUT_TOKENS`.

Reducing the formal candidate set or silently skipping batches is not a cost
control option. Use the pipeline's generic deterministic exclusions and staged
gater/deep-analysis design.

## Throughput

Formal execution uses bounded stage-specific concurrency. Recommended initial
MiniMax settings are:

```bash
export MODEL_GATER_BATCH_SIZE=3
export MODEL_DEEP_BATCH_SIZE=2
export MODEL_GATER_CONCURRENCY=3
export MODEL_DEEP_CONCURRENCY=3
export MODEL_MAX_IN_FLIGHT_REQUESTS=3
```

Failed batches do not stop other runnable batches. Authentication,
configuration, and connection failures are not expanded into wasteful
single-trial calls. The adapter deterministically coalesces complementary risk
and efficacy rows when a provider emits them separately for the same trial.
When a multi-trial response still fails schema or exact-ID validation, the
executor immediately falls back to resumable single-trial jobs instead of
repeatedly submitting the same long batch. Network and single-trial failures
retain normal retry behavior.

`MODEL_COMPACT_DEEP_PROMPT=1` is the default. It omits eligibility text already
adjudicated by the authoritative gater result, loads only risk rules applicable
to the current batch, and requests bounded concise narratives while preserving
every required clinical field. Set it to `0` only for prompt diagnostics or
compatibility comparisons.

Each stage can select a different provider/model with the
`GATER_MODEL_*`, `DEEP_MODEL_*`, and `DECISION_MODEL_*` variables. The run state
records all three model names.

Before deep analysis, the formal executor queries the official Europe PMC REST
API concurrently and caches candidates under `publication-cache/`. The model
receives these auditable candidates and analyzes applicability; it is not asked
to pretend that an ordinary text-generation request has live web access.
