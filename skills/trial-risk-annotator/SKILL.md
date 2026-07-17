---
name: trial-risk-annotator
description: Use when annotating a clinical trial's mechanism-specific risks for a specific patient and cancer type. Triggers when the parent clinical-trial-matching skill needs risk narratives for the report. Replaces v1.7.x risk_lookup.py + risk_taxonomy.json (which leaked PDAC-specific risk text onto CRC reports because the taxonomy was keyed on mechanism only, not (mechanism × cancer)).
license: MIT
metadata:
  author: CancerDAO
  version: "2.0.0"
  parent_skill: clinical-trial-matching
---

# trial-risk-annotator

You generate patient-specific, cancer-specific risk annotations for a given trial's mechanism of action. The output goes into the report's "风险标记" block per decision path.

## The bug this subskill exists to fix

v1.7.x had `risk_taxonomy.json` keyed on mechanism only (e.g. `"egfr_combo_pdac": {...narrative about EGFR combo in PDAC...}`). The `risk_lookup.py` would attach this risk to ANY trial whose mechanism matched, regardless of patient cancer type. Result: a CRC patient on a Calderasib (KRAS G12C) trial for advanced solid tumors got the risk note "在 **PDAC** 中常作为 KRAS G12D / G12C 抑制剂的联合伙伴 (克服 EGFR-feedback)" — wrong cancer context, sounds clinically authoritative, but doesn't apply to CRC.

**v2 rule**: every risk annotation MUST be triple-grounded in (mechanism, cancer_type, patient_state). No risk template gets emitted unless all three are checked.

## Inputs

```json
{
  "trial": {
    "id": "NCT...",
    "title": "...",
    "phases": [...],
    "interventions": ["sotorasib", "cetuximab"],
    "mechanism_of_action": "KRAS G12C inhibitor + anti-EGFR mAb"
  },
  "patient": { /* full patient.json */ }
}
```

## Output

```json
{
  "trial_id": "NCT...",
  "risks": [
    {
      "key": "kras_g12c_inhibitor_class",
      "mechanism": "KRAS G12C covalent inhibitor",
      "cancer_context": "CRC (patient's tumor type)",
      "risk_level": "moderate",
      "narrative": [
        "KRAS G12C inhibitor monotherapy in CRC has substantially lower ORR than NSCLC (CRC ~10%, NSCLC ~30-40%) due to adaptive EGFR feedback unique to CRC biology",
        "Combination with anti-EGFR mAb (cetuximab/panitumumab) restores ORR to ~30% per CodeBreaK 300 (sotorasib + panitumumab vs investigator choice)",
        "If trial is monotherapy in CRC cohort, expect lower ORR; if trial includes anti-EGFR combo arm, mention this paradigm to patient"
      ],
      "applies_because": "Trial intervention includes KRAS G12C inhibitor; patient cancer is CRC"
    }
  ]
}
```

## Process

```
1. Identify the trial's mechanism(s) of action from interventions
2. For each mechanism, evaluate (mechanism, patient.cancer_type, patient.prior_therapies):
   - Look up rules/{mechanism}-{cancer}.md if it exists (most specific)
   - Otherwise rules/{mechanism}.md with cancer-specific notes inline
   - Otherwise emit narrative from training knowledge with explicit grounding
3. For each risk, write narrative that names the cancer context explicitly
4. Tag risk_level: low | moderate | high | high_uncertainty
5. Filter out any risk not actually applicable to this (mechanism, cancer) pair
```

## Risk-level taxonomy

| Level | Meaning |
|---|---|
| `low` | Well-characterized risk, established management protocol |
| `moderate` | Predictable AE pattern, may require dose modification or supportive care |
| `high` | Significant patient-specific concern (comorbidity interaction, prior failure mode) |
| `high_uncertainty` | First-in-class / phase 1 dose escalation / limited published data — outcomes unpredictable |

## Mandatory grounding check

Before emitting any risk narrative, verify:

1. ✅ Does this risk apply to the patient's specific cancer type? (Reject if narrative is from a different cancer context — see PDAC-leak-to-CRC example)
2. ✅ Does this risk consider the patient's prior therapy load? (e.g. don't warn about "PD-1 toxicity" for a patient who's been on camrelizumab for a year without irAE)
3. ✅ Is the narrative specific enough to be actionable? (Reject "watch for AEs" — name the AE, name the management)

If a risk doesn't pass these checks, omit it.

## Reference: cancer-specific patterns

- [KRAS G12C inhibitor risks across cancers](rules/risk-kras-g12c-by-cancer.md)
- [KRAS G12D inhibitor (only PDAC has mature data)](rules/risk-kras-g12d-class.md)
- [pan-RAS / RAS-ON inhibitors](rules/risk-pan-ras-class.md)
- [Cell therapy for solid tumors (CAR-T, TIL, TCR-T)](rules/risk-cell-therapy-solid-tumor.md)
- [Bispecific antibody in MSS CRC](rules/risk-bispecific-mss-crc.md)
- [Phase 1 dose escalation generic risks](rules/risk-phase-1-dose-escalation.md)
- [Output schema](rules/output-risk-annotation-schema.md)
