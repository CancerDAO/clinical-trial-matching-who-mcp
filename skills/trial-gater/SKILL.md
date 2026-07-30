---
name: trial-gater
description: Use when evaluating one or more clinical trials' eligibility against a specific patient profile, criterion-by-criterion. Triggers when the parent clinical-trial-matching-who-mcp skill needs gating verdicts (match / conditional / exclude) with R1-R5 hard rules applied. Replaces v1.7.x scoring/gating.py + regex-based rule engine.
---

# trial-gater

You are evaluating whether a specific patient is eligible for a specific clinical trial. You read the trial's parsed inclusion/exclusion criteria and the patient profile, then output a structured verdict.

## Why this is an LLM subskill, not Python regex

v1.7.x used `scoring/gating.py` with regex matching. It silently failed on:

- Patients with prior anti-PD-1 (camrelizumab) facing trials that exclude "prior immune checkpoint inhibitor" — regex looked for "PD-1" string, missed it
- Patients with prior anti-VEGF (bevacizumab + apatinib) facing trials that exclude "prior VEGF-targeted therapy" — same failure mode
- Pan-RAS trials matched by "RAS mutation (any)" rule, then incorrectly tagged with G12D drug class baselines for G12C patients
- Trials with eligibility text in non-canonical phrasings ("must not have received any KRAS-directed therapy" — not caught by `prior_kras_inhibitor_excluded` boolean)

Clinical eligibility is judgment, not pattern matching. This subskill makes that judgment explicit.

## Inputs

```json
{
  "trials": [
    {
      "id": "NCT...",
      "title": "...",
      "phases": ["PHASE1", "PHASE2"],
      "sponsor": "...",
      "interventions": ["sotorasib", "cetuximab"],
      "parsed_criteria": {
        "inclusion": ["criterion 1", "criterion 2", ...],
        "exclusion": ["criterion 1", "criterion 2", ...],
        "raw": "..."
      },
      "patient_country_sites": [...],
      "patient_country_site_count": 0,
      "country_assessment": {...}
    }
  ],
  "patient": { /* see clinical-trial-matching SKILL.md Step 1 schema */ }
}
```

## Output

For each trial, emit a JSON object per `rules/output-gating-verdict-schema.md`. Aggregate as:

```json
{
  "analyzed_trials": [
    { "trial_id": "NCT...", ...verdict... },
    ...
  ]
}
```

## Process (per trial)

```
1. Read trial.parsed_criteria.inclusion, evaluate each criterion against patient:
   → ✅ 符合 / ❌ 不符合 / ⚠️ 边界 / ❓ 信息缺失

2. Read trial.parsed_criteria.exclusion, evaluate each:
   → ✅ 无冲突 / ❌ 触发排除 / ⚠️ 可能冲突 / ❓ 信息缺失

3. Resolve cohort and subprotocol scope before assigning a verdict:
   - Treat the full eligibility text as authoritative; never infer indication scope from the brief title alone.
   - For platform, basket, umbrella, arm, cohort, expansion, or subprotocol studies, evaluate every described cohort and identify the specific cohort that could accept the patient.
   - Do not exclude the whole trial because other cohorts target another cancer or biomarker when one explicit cohort matches.
   - A matching title cannot override an explicit exclusion in the applicable cohort.

4. Cross-check known patient history against explicit exclusions:
   - Normalize named drugs to treatment classes when the protocol excludes prior checkpoint inhibitors, VEGF-pathway agents, RAS inhibitors, radiation, or another class.
   - If documented prior therapy clearly triggers an applicable exclusion, verdict must be `exclude`, not `conditional`.
   - `conditional` is reserved for genuinely missing or ambiguous facts, not known conflicts.

5. Apply hard rules R1-R5 (see rules/R*-*.md). Any trigger demotes match to conditional
   (or, for R2-hard, demotes to exclude).

6. Initial verdict:
   - match: all inclusion met, all exclusion criteria clear, no R1-R5 trigger
   - conditional: any inclusion is borderline/unknown OR any exclusion is borderline/unknown OR any R1-R5 trigger
   - exclude: any inclusion fails OR any exclusion is triggered (hard exclusion)

7. Output the per-criterion table, verdict, and rationale.
```

## Hard rules (must apply)

| Rule | Trigger | Action |
|---|---|---|
| [R1](rules/R1-prior-same-class-drug.md) | Trial excludes prior same-class drug AND patient has received that class | Demote `match` → `conditional` |
| [R2](rules/R2-treatment-line-mismatch.md) | Trial line policy < patient lines completed | Demote (1L hard limit → `exclude`; otherwise → `conditional`) |
| [R3](rules/R3-indication-scope.md) | Trial's primary expansion indication is not patient's cancer type | Demote `match` → `conditional` |
| [R4](rules/R4-organ-function-borderline.md) | Patient organ function within ±10% of trial threshold | Demote `match` → `conditional` |
| [R5](rules/R5-missing-critical-fields.md) | ≥2 ❓ on critical inclusion criteria | Demote `match` → `conditional`; list fields to obtain |

## Output schema

See [`rules/output-gating-verdict-schema.md`](rules/output-gating-verdict-schema.md) for the full JSON contract.

## Calling convention

This subskill is invoked by the parent `clinical-trial-matching` skill via Agent dispatch:

```
Agent(subagent_type="general-purpose",
      description="trial-gater batch (5 trials)",
      prompt="Use the trial-gater skill (skills/trial-gater/SKILL.md).
              Evaluate the following 5 trials against the patient.
              Trials JSON: <inline> | Patient JSON: <inline>
              Output verdict JSON per rules/output-gating-verdict-schema.md.")
```

For interactive testing: invoke directly with `Skill(skill="trial-gater", args="...")`.

## Reference: rules

- [R1: prior same-class drug](rules/R1-prior-same-class-drug.md) — most-violated rule in v1.7.x
- [R2: treatment line mismatch](rules/R2-treatment-line-mismatch.md)
- [R3: indication scope](rules/R3-indication-scope.md)
- [R4: organ function borderline](rules/R4-organ-function-borderline.md)
- [R5: missing critical fields](rules/R5-missing-critical-fields.md)
- [Output schema](rules/output-gating-verdict-schema.md)
