# R4 — Organ function borderline

## Rule

If the patient's lab values are within ±10% of the trial's organ-function threshold, demote `match` → `conditional`. Day-of-screening labs may shift the patient in or out, so the call needs to be made then, not now.

## Common thresholds and the ±10% band

| Organ | Common trial threshold | "Borderline" band (90%–threshold) |
|---|---|---|
| Renal (eGFR) | ≥60 mL/min/1.73m² | 54–59 mL/min/1.73m² |
| Renal (Cr clearance) | ≥50 mL/min | 45–49 mL/min |
| Hepatic (AST/ALT) | ≤2.5× ULN (≤5× if liver mets) | within 10% of upper limit |
| Hepatic (bilirubin) | ≤1.5× ULN | within 10% of upper limit |
| Hematologic (ANC) | ≥1.5 × 10⁹/L | 1.35–1.5 × 10⁹/L |
| Hematologic (platelets) | ≥100 × 10⁹/L | 90–100 × 10⁹/L |
| Hematologic (Hgb) | ≥90 g/L (or ≥100 for some) | 81–90 g/L (or 90–100) |
| Cardiac (LVEF) | ≥50% (cell therapy often ≥45%) | 45–50% (or 40–45%) |

## How to apply

For each organ-function inclusion criterion in the trial:

1. Identify threshold (e.g. "eGFR ≥ 60 mL/min/1.73m²")
2. Locate the matching value in `patient.organ_function` or `patient.key_lab_trends`
3. Compute: is patient value within ±10% of threshold?
4. If yes, mark criterion as `⚠️ 边界` and set R4_triggered.

## Synthetic later-line CRC example

Patient had "renal dysfunction recent" annotation in v1.7.x but no specific eGFR captured. Many KRAS G12C trials require eGFR ≥ 60. **trial-gater should flag this as ❓ 信息缺失 + R4 latent risk**, and emit a request for the screening lab in the action items. v1.7.x silently passed it as ✅.

## Decision

```
if patient_value missing:
    mark ❓ 信息缺失, list in action items, no R4 yet
elif patient_value < threshold:
    mark ❌ 不符合 (hard fail)
elif patient_value within (threshold, threshold * 1.10):
    mark ⚠️ 边界 + R4 → conditional
else:
    mark ✅ 符合
```

## Output marker

```json
{
  "hard_rules_triggered": ["R4"],
  "R4_detail": [
    {
      "criterion": "eGFR ≥ 60 mL/min/1.73m²",
      "patient_value": 58.93,
      "threshold": 60,
      "deviation_pct": -1.78
    }
  ]
}
```
