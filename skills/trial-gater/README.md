# trial-gater

LLM subskill for evaluating clinical trial eligibility against a specific patient profile, criterion-by-criterion, with R1-R5 hard rules applied.

## Install

```bash
# Standalone (for testing)
npx skills add CancerDAO/clinical-trial-matching-skill --skill trial-gater

# Or with the parent skill (recommended)
npx skills add CancerDAO/clinical-trial-matching-skill
```

## What it does

For each trial in a batch, this subskill:

1. Reads the trial's parsed inclusion / exclusion criteria
2. Compares each criterion to the patient profile
3. Marks criteria ✅ 符合 / ❌ 不符合 / ⚠️ 边界 / ❓ 信息缺失
4. Applies R1-R5 hard rules:
   - **R1**: prior same-class drug → demote
   - **R2**: treatment line mismatch → demote (1L-only is hard exclude)
   - **R3**: indication scope (patient cancer not in primary expansion) → demote
   - **R4**: organ function within ±10% of threshold → demote
   - **R5**: ≥2 critical fields missing → demote + emit data-to-obtain list
5. Emits a verdict (`match` / `conditional` / `exclude`) with rationale

Replaces v1.7.x `scoring/gating.py` regex matcher (which silently failed on patients with prior anti-PD-1 / anti-VEGF because the regex was hardcoded to KRAS-specific phrasings).

## Rules

- [R1: prior same-class drug](rules/R1-prior-same-class-drug.md)
- [R2: treatment line mismatch](rules/R2-treatment-line-mismatch.md)
- [R3: indication scope](rules/R3-indication-scope.md)
- [R4: organ function borderline](rules/R4-organ-function-borderline.md)
- [R5: missing critical fields](rules/R5-missing-critical-fields.md)
- [Output schema](rules/output-gating-verdict-schema.md)

## See also

- Parent: [`clinical-trial-matching`](../clinical-trial-matching/)
- Sibling subskills: [`trial-risk-annotator`](../trial-risk-annotator/), [`trial-efficacy-contextualizer`](../trial-efficacy-contextualizer/), [`decision-synthesizer`](../decision-synthesizer/)
