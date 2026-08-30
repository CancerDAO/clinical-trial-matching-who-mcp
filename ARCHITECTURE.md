# Architecture

The formal workflow has one stateful entry point:

```text
Cancer Buddy archive or legacy patient JSON
-> patient_input.py
-> normalized-patient.json
-> core (or expanded) WHO MCP retrieval + WHO portal delta
-> WHO verifier/deduplicator
-> generic structured hard rules
-> recall triage + A/B/C analysis priority
-> direct-registry verification of the coverage target set
-> trial-gater (Band A; Band B only in --coverage full)
-> publication prefetch
-> risk + efficacy deep analysis (Band A match/conditional)
-> evidence_grounding.py
-> decision-synthesizer
-> decision_grounding.py
-> full_pipeline.py finalize
-> patient report.html, optional clinician-report.html, run manifest
```

## Module ownership

| Area | Owner | Responsibility |
|---|---|---|
| Patient input | `pipeline/patient_input.py` | Detect legacy JSON or Cancer Buddy archive, preserve unknown/disputed facts, emit one normalized patient snapshot |
| Search plan | `retrieval/search_plan.py` | Validate a supplied plan; default baseline is core dimensions (disease+biomarker, pan-tumor, named drug, regional terms) with optional eight-dimension expansion |
| Retrieval | `retrieval/` | Execute the compiled plan through MCP, unique `get_trial` IDs, optional `MCP_FETCH_DETAILS=0` |
| Registry truth | `verification/` | Enrich, deduplicate, separate country records from named sites, and attempt direct live-status checks on the coverage target set |
| Deterministic triage | `pipeline/generic_hard_rules.py`, `pipeline/recall_triage.py`, `pipeline/analysis_priority.py` | Exclude only explicit structured contradictions; assign A/B/C analysis bands without inferring eligibility |
| Clinical contracts | `pipeline/analysis_contract.py` | Compact gater payloads, Band A deep jobs, validate gater/deep outputs |
| Model transport | `pipeline/model_api_runner.py`, `cli_model_runner.py` | Call one configured model backend |
| Batch reliability | `pipeline/model_batch_executor.py` | Exact ID coverage, retry, quarantine, split recovery, circuit breaking |
| Publication retrieval | `pipeline/publication_prefetch.py` | Fetch and cache auditable Europe PMC candidates |
| Evidence authority | `pipeline/evidence_grounding.py` | Reject model-added publications and restore publication identity from prefetch records |
| Decision authority | `pipeline/decision_grounding.py` | Restore eligibility, efficacy, risk, blockers, and timeline limits from validated upstream data |
| State machine | `pipeline/run_formal_pipeline.py` | Enforce stage order and resume a formal run |
| Final quality gate | `pipeline/full_pipeline.py` | Enforce coverage, retrieval, freshness, and produce the only formal report |
| Report translation | `render/report_translation.py` | Translate only China-patient narratives through configured model APIs while preserving identifiers and clinical decisions |
| Presentation | `presentation/`, `render/` | Titles, links, geography grouping, mechanism sections, HTML |

The retrieval boundary compiles every disease condition and its
biomarker/mechanism/modality term into one conjunctive FTS query. Formal plans
reject patient-disease-only queries. Default generated recall is core-first;
combination, pathway, cell-therapy, and immune branches are added when
`matching_context.search_terms` supplies them or `SEARCH_EXPANDED_RECALL=1`.
Post-detail deduplication merges only authoritative registry-ID bridges;
title/intervention lookalikes remain separate with an audit flag.

## Formal invariants

1. Every recalled ID has exactly one auditable disposition: hard exclusion, deferred/Band C audit, compact Band B gater (full coverage), or Band A gater.
2. Every Band A `match` or `conditional` ID receives risk, efficacy, and publication-search output. Untagged historical jobs keep the old all-match/conditional deep contract.
3. Every displayed publication resolves to a deterministic prefetch candidate.
4. Direct-registry verification runs on the coverage target set (Band A in patient mode; hard-rule pass in full mode). A current WHO portal delta does not substitute for direct status verification.
5. Unknown or disputed patient facts remain unknown and are never inferred from language, filenames, or treatment ordering.
6. Only `run_formal_pipeline.py` may orchestrate a formal run, and only `full_pipeline.py finalize` may promote `report.html`.
7. `report.html` is the patient handoff (top verification paths + in-country recruiting). `clinician-report.html` is the audit workbook and is emitted only when `--coverage full` passes.

## Coverage modes

`ANALYSIS_COVERAGE=patient` (default) spends model budget on Band A: disease/molecular primary hits that are in-country or recruiting. Band B stays an auditable deferred disposition unless fallback promotion fills an empty Band A. `ANALYSIS_COVERAGE=full` or `--coverage full` still gates Band B with compact gater input but does not run deep analysis on those rows.
