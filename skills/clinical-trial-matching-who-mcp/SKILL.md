---
name: clinical-trial-matching-who-mcp
description: Use for generic multi-cancer clinical-trial matching through the WHO ICTRP MCP database while preserving the original model-executed gating, risk, efficacy and decision subskills.
license: MIT
metadata:
  author: CancerDAO
  version: "3.0.0"
---

# Generic WHO MCP clinical-trial matching

This skill changes the retrieval and registry-verification boundary. It does not replace the original clinical reasoning subskills with Python keyword rules.

## Non-negotiable architecture

`patient structure + original eight-dimensional plan` -> `real WHO MCP` -> `one verifier/deduplicator` -> `generic structured hard-rule triage` -> `trial-gater for every remaining trial` -> `risk/efficacy/evidence only for match or conditional` -> `decision-synthesizer` -> `mechanism classifier` -> `one patient-report renderer`.

A formal report has two executable stages separated by model work:

1. `full_pipeline.py prepare` calls the MCP server through JSON-RPC stdio, retrieves metadata, runs every search branch, calls `get_trial`, verifies/deduplicates details, computes operational feasibility and writes `analysis_jobs.json`.
2. The model first executes canonical `trial-gater` for every non-hard-excluded candidate. `analysis_batch_manager.py deep-jobs` then creates risk/efficacy/evidence work only for `match` and `conditional` verdicts. Model-gated exclusions remain in the full audit without paying for deep analysis. `decision-synthesizer` runs once after both stages.
3. `full_pipeline.py finalize` validates every subskill contract and renders only after complete coverage. It rejects heuristic/example analysis and missing trial outputs.

The canonical subskills are sibling directories, without `-who-mcp` forks:

- `../trial-gater/SKILL.md`
- `../trial-risk-annotator/SKILL.md`
- `../trial-efficacy-contextualizer/SKILL.md`
- `../decision-synthesizer/SKILL.md`

## Patient and search plan

Preserve the original structured patient fields, including cancer type, stage, biomarkers, molecular variants, treatment lines, current treatment, prior therapies/classes, performance status, organ function, comorbidities, country, city, travel willingness and affordability.

The search plan must contain all original dimensions:

1. disease plus exact biomarker;
2. pan-tumor biomarker recall;
3. rational combination targets;
4. pathway and resistance strategies;
5. named approved/investigational agents;
6. cell and biologic therapy;
7. immune strategies;
8. Chinese-registry terms.

Do not filter the first-pass recall by patient country.

## MCP retrieval and verification

Use the real stdio MCP tools `database_metadata`, `execute_search_plan`, and `get_trial`. Persist `database_as_of`, MCP protocol/server metadata, query audit, pagination and truncation fields.

`who_mcp_verifier.py` is the only final deduplication authority. It uses canonical primary/secondary registry IDs, normalized CTIS IDs and strict protocol-core identifiers. Title similarity is never sufficient for deduplication.

Keep named sites separate from country-only records. A national registry ID may be displayed under in-country access, but the card must state that a named center is unverified. A model may summarize location evidence; it may not invent a center.

## Model analysis contract

For every candidate that passes conservative structured hard rules, `trial-gater` must run. For every `match` or `conditional` result:

- `trial-gater` evaluates criterion by criterion and applies R1-R5.
- `trial-risk-annotator` grounds every risk in mechanism × patient cancer × patient state.
- The trial-efficacy-contextualizer performs an auditable publication search for every non-excluded trial, supplies a development evidence chain plus applicable efficacy evidence, or explicitly records no_relevant_publication/no_data; it must not transfer another cancer or mutation baseline without a caveat.
- `decision-synthesizer` runs after all per-trial outputs and may not promote an excluded trial.

The analysis bundle must use schema `clinical-subskills-analysis-v1` and provenance `mode=llm_subskills`. See `scripts/pipeline/analysis_contract.py`. A missing/invalid bundle is a hard stop, not a reason to fall back to deterministic clinical heuristics.

## Mechanism and feasibility

Mechanism classification is a report axis, independent of eligibility. Use the seven flat groups in `mechanism_categories.py`.

Feasibility remains operational and patient-relative. Geographic and financial dimensions may be computed for explanation but currently have zero composite weight. No feasibility score can override an exclusion verdict.

## Report contract

Use only `scripts/render/html_renderer.py`. The report follows the patient-triage layout, groups trials by mechanism and provides All / In-country access / Country record unverified / Overseas filters. Mechanism counts must update with the active filter.

China patients receive Chinese report framing; other patients receive English framing. Detailed analysis text should be emitted by the model in the same language as the report.

## Commands

```powershell
python scripts/pipeline/full_pipeline.py prepare `
  --patient patient.json --plan search-plan.json --db trials.db `
  --mcp-python python --mcp-server server.py --out run
```

After all `gater-batch-*.json` files are complete, materialize the reduced deep workload:

```powershell
python scripts/pipeline/analysis_batch_manager.py deep-jobs `
  --jobs run/analysis_jobs.json --patient patient.json `
  --gater-batch-dir run/batches --out run/deep_jobs.json
```

After the risk/efficacy/evidence `deep-batch-*.json` files and the decision output are complete, merge both stages:

```powershell
python scripts/pipeline/analysis_batch_manager.py merge `
  --jobs run/analysis_jobs.json --patient patient.json `
  --batch-dir run/batches --deep-batch-dir run/deep-batches `
  --decision run/decision_report.json --out run/analysis_bundle.json `
  --model MODEL_NAME --output-language zh-CN
```

After the canonical subskills produce `analysis_bundle.json`:

```powershell
python scripts/pipeline/full_pipeline.py finalize `
  --prepared run/prepared.json --analysis run/analysis_bundle.json --out run/final
```

## Quality gates

- Reject incomplete eight-dimensional plans.
- Reject global MCP truncation; retain per-query pagination/truncation audit.
- Reject formal reports without complete validated LLM subskill output.
- Reject risk output whose cancer context differs from the patient.
- Reject efficacy estimates without applicability reasoning and evidence source.
- Preserve database watermark and portal-delta limitation.
- Do not expose credentials in project files.
## Formal readiness semantics

A positive analysis-limit or prefilter-limit is validation-only. Both default to zero. Formal staged runs require every recalled trial to receive either an auditable deterministic hard exclusion or a model gater verdict, and every `match` or `conditional` verdict to receive validated risk, efficacy and development-evidence output.

finalize may render a validation artifact for engineering review, but formal_report_ready is true only when all three gates pass:

1. every recalled trial has a hard-rule or gater disposition, every non-excluded trial has complete deep analysis, and there are no budget omissions;
2. neither global nor per-query MCP retrieval is truncated;
3. the WHO portal delta artifact is executed against the exact current database_as_of watermark.

The jobs contract carries target_language. Patient-facing rationale, eligibility, risk and efficacy narratives must be written in that language.
