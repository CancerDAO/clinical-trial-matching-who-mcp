# trial-gater output schema

Per-trial JSON contract. All fields required unless marked optional.

```json
{
  "trial_id": "NCT07209111",
  "verdict": "match | conditional | exclude",
  "confidence": 0.85,

  "inclusion_evaluation": [
    {
      "criterion": "Histologically confirmed KRAS G12C-mutated solid tumor",
      "verdict": "✅ 符合",
      "evidence": "Patient profile lists KRAS G12C from 2022 NGS report"
    },
    {
      "criterion": "Measurable disease per RECIST 1.1",
      "verdict": "❓ 信息缺失",
      "evidence": "No imaging in dataset for cycle 8; latest measurable assessment was 2024-09-05 CT"
    }
  ],

  "exclusion_evaluation": [
    {
      "criterion": "Prior treatment with a covalent KRAS G12C inhibitor",
      "verdict": "✅ 无冲突",
      "evidence": "Patient is KRAS G12C inhibitor naive"
    },
    {
      "criterion": "Active CNS metastases",
      "verdict": "❓ 信息缺失",
      "evidence": "No brain MRI in dataset"
    }
  ],

  "hard_rules_triggered": ["R4", "R5"],
  "R1_detail": null,
  "R2_detail": null,
  "R3_detail": null,
  "R4_detail": [
    {
      "criterion": "eGFR ≥ 60 mL/min/1.73m²",
      "patient_value": null,
      "threshold": 60,
      "note": "Patient has 'renal dysfunction recent' but no specific eGFR captured — flag for screening labs"
    }
  ],
  "R5_detail": {
    "critical_unknowns_count": 2,
    "fields_to_obtain": ["Brain MRI", "Updated eGFR"]
  },

  "rationale": "Patient is KRAS G12C inhibitor naive (✅ R1) and has 2 lines completed (✅ R2 — trial requires ≥1 prior line). CRC is named in expansion cohorts (✅ R3). However, eGFR not documented and brain MRI missing — both gating-relevant. Demote to conditional pending screening data.",

  "blockers_satisfied": ["KRAS G12C mutation match", "≥1 prior line", "Stage IV"],
  "blockers_failed": [],
  "blockers_pending": ["Renal function lab", "CNS imaging"],
  "advisors_unknown": ["HBV/HCV/HIV serology"]
}
```

## Field semantics

- `verdict`: terminal classification used by downstream synthesis. `match` = strict no-issues. `conditional` = matchable but needs caveat or data. `exclude` = hard fail (R2-hard, R3-hard, or any inclusion ❌).
- `confidence`: 0.0–1.0, your own confidence in the verdict given criterion ambiguity. Used by `decision-synthesizer` for ranking.
- `hard_rules_triggered`: list of R1–R5 strings; absence means no hard rule fired.
- `R{N}_detail`: object per the rule's own schema, or `null` if not triggered.
- `rationale`: 1–3 sentence human-readable explanation, suitable for inclusion in the patient report's "为什么是这条" block.
- `blockers_*` and `advisors_unknown`: bucketed criteria summary for HTML render compatibility (matches v1.7.x feasibility input shape so html_renderer.py keeps working).

## Aggregate output

When processing a batch:

```json
{
  "results": [ {trial1}, {trial2}, ... ],
  "summary": {
    "match": <count>,
    "conditional": <count>,
    "exclude": <count>,
    "hard_rule_distribution": {"R1": N, "R2": N, "R3": N, "R4": N, "R5": N}
  }
}
```
