# R5 — Missing critical fields

## Rule

If ≥2 of the trial's CRITICAL inclusion criteria are evaluated as `❓ 信息缺失` (missing patient data, not insufficient/conflict), demote `match` → `conditional` AND emit an action-items list of which patient data to obtain before screening.

## What counts as "critical"

A criterion is critical if any of these are true:

1. It's a molecular requirement (mutation status, IHC expression, biomarker level)
2. It's an organ-function lab value (renal, hepatic, hematologic, cardiac)
3. It's a measurable disease requirement (RECIST 1.1 measurable lesion)
4. It's a CNS imaging requirement (no brain mets confirmed by MRI)
5. It's a viral serology requirement (HBV/HCV/HIV)

Non-critical (do not count toward R5 threshold):
- Demographics (age cutoff usually well-known)
- ECOG (default-pass per parent skill)
- Comorbidity-related exclusions where the patient has detailed comorbidity record
- Concomitant medications (usually addressable at screening)

## How to apply

```
critical_unknowns = count(criteria where critical=true AND verdict="❓ 信息缺失")
if critical_unknowns >= 2:
    R5 triggered → conditional
    emit_action_items(criteria_unknown)
```

## Why this matters

A trial flagged "match" with 4 ❓ entries is not a real match — it's an unknown. The patient's care team will be told "you're a candidate", spend 2 weeks gathering screening data, and discover the patient was never eligible. R5 prevents that by gating on data availability.

## Output marker

```json
{
  "hard_rules_triggered": ["R5"],
  "R5_detail": {
    "critical_unknowns_count": 3,
    "fields_to_obtain": [
      "Latest CT scan with measurable disease per RECIST 1.1",
      "HBV/HCV/HIV serology",
      "Brain MRI to rule out CNS mets"
    ]
  }
}
```
