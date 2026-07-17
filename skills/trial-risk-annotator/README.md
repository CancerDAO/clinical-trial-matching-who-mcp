# trial-risk-annotator

LLM subskill that generates patient-specific, cancer-specific risk annotations for a given trial's mechanism of action.

## Install

```bash
# Standalone
npx skills add CancerDAO/clinical-trial-matching-skill --skill trial-risk-annotator

# With parent skill
npx skills add CancerDAO/clinical-trial-matching-skill
```

## What it does

For each trial, this subskill:

1. Identifies trial mechanism(s) of action from interventions
2. For each (mechanism × patient.cancer_type × patient prior therapies), generates a risk narrative with explicit grounding
3. Filters out risks not actually applicable to the patient's cancer
4. Emits structured risk annotations with `risk_level` (low / moderate / high / high_uncertainty)

Replaces v1.7.x `risk_taxonomy.json` lookup, which keyed on mechanism only and leaked PDAC-specific risk text onto CRC reports.

## Mandatory grounding

Every risk emitted MUST declare `applies_because: (mechanism × cancer × patient)`. The schema enforces this — no risk gets through without a grounding statement.

## Rules

- [KRAS G12C inhibitor by cancer](rules/risk-kras-g12c-by-cancer.md) — NSCLC vs CRC vs PDAC
- [KRAS G12D class](rules/risk-kras-g12d-class.md)
- [Pan-RAS / RAS-ON class](rules/risk-pan-ras-class.md)
- [Cell therapy in solid tumors](rules/risk-cell-therapy-solid-tumor.md)
- [Bispecific antibody in MSS CRC](rules/risk-bispecific-mss-crc.md)
- [Phase 1 dose escalation overlay](rules/risk-phase-1-dose-escalation.md)
- [Output schema](rules/output-risk-annotation-schema.md)

For cancers / mechanisms without a dedicated rule file, the LLM generates risk narratives from training knowledge (still grounded by the schema).

## See also

- Parent: [`clinical-trial-matching`](../clinical-trial-matching/)
- Sibling subskills: [`trial-gater`](../trial-gater/), [`trial-efficacy-contextualizer`](../trial-efficacy-contextualizer/), [`decision-synthesizer`](../decision-synthesizer/)
