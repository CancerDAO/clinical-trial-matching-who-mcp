# trial-risk-annotator output schema

```json
{
  "trial_id": "NCT07209111",
  "trial_mechanisms_identified": [
    "KRAS G12C covalent inhibitor",
    "Phase 2 (no dose-escalation overlay)"
  ],
  "patient_cancer_context": "CRC",
  "risks": [
    {
      "key": "kras_g12c_crc",
      "mechanism": "KRAS G12C covalent inhibitor",
      "cancer_context": "CRC (patient's tumor type)",
      "risk_level": "moderate",
      "narrative": [
        "string narrative bullet 1",
        "string narrative bullet 2",
        "..."
      ],
      "applies_because": "Trial intervention is calderasib (KRAS G12C inhibitor); patient cancer type is CRC"
    }
  ],
  "risks_considered_but_omitted": [
    {
      "key_skipped": "kras_g12c_pdac",
      "reason": "Patient cancer is CRC, not PDAC — PDAC narrative not applicable"
    }
  ]
}
```

## Required fields

- `trial_id` — must match input trial ID
- `trial_mechanisms_identified` — explicit list of mechanisms detected from interventions; used by verifier to check coverage
- `patient_cancer_context` — explicit echo of patient.cancer_type for grounding audit
- `risks[].applies_because` — REQUIRED — must explain why this risk applies to this (mechanism × cancer × patient) combination. If you can't justify it, omit the risk.
- `risks_considered_but_omitted` — show what was filtered. This is the audit trail proving you didn't blindly attach mechanism-only risks.

## Empty case

If no risks apply, emit:
```json
{
  "trial_id": "NCT...",
  "trial_mechanisms_identified": [...],
  "patient_cancer_context": "CRC",
  "risks": [],
  "risks_considered_but_omitted": [...]
}
```

This is preferable to emitting low-quality boilerplate ("watch for AEs"). The downstream report will simply skip the risk block for that trial.
