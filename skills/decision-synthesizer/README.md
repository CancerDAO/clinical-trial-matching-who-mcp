# decision-synthesizer

LLM subskill that synthesizes per-trial gating + risk + efficacy outputs into a Top-N decision report with diversity bucketing, Goals-of-Care trigger, and patient consistency flags.

## Install

```bash
# Standalone
npx skills add CancerDAO/clinical-trial-matching-skill --skill decision-synthesizer

# With parent skill
npx skills add CancerDAO/clinical-trial-matching-skill
```

## What it does

This subskill is invoked once after `trial-gater` + `trial-risk-annotator` + `trial-efficacy-contextualizer` have produced per-trial outputs. It:

1. Echoes the patient summary + runs internal-consistency checks (timeline gaps, response classification mismatches, comorbidity-treatment compatibility, lab anomalies)
2. Evaluates the Goals-of-Care trigger using `effective_line = treatment_lines_completed + (1 if current_therapy_ongoing else 0)` against cancer-type ontology median OS
3. Selects Top-N decision paths with diversity bucketing (primary / alternative-mechanism / cell-therapy or overseas slots)
4. Emits SoC benchmarks for the patient's current line
5. Cross-validates that risk narratives are cancer-context-grounded and efficacy class-baselines match patient mutation

Replaces v1.7.x `synthesis/decision_paths.py` + `goals_of_care.py` + `consistency_check.py`, which:
- Returned empty `patient_summary={}` and `feasibility_score=None` despite stdout printing correct values
- Missed GoC trigger for L3-ongoing patients (used `treatment_lines_completed` excluding ongoing line)
- Forced diversity bucketing without checking class compatibility (e.g. KRAS G12D drug as #3 path for a G12C patient)

## Output

Produces `decision_report.json`, the input to the deterministic Python `html_renderer.py`. See [output schema](rules/output-decision-report-schema.md) for the contract.

## Rules

- [Diversity bucketing for Top-N](rules/synthesis-diversity-bucketing.md)
- [Goals-of-Care trigger](rules/synthesis-goals-of-care-trigger.md)
- [Output schema](rules/output-decision-report-schema.md)

## See also

- Parent: [`clinical-trial-matching`](../clinical-trial-matching/)
- Sibling subskills: [`trial-gater`](../trial-gater/), [`trial-risk-annotator`](../trial-risk-annotator/), [`trial-efficacy-contextualizer`](../trial-efficacy-contextualizer/)
