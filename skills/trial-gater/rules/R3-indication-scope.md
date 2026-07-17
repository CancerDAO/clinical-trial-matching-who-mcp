# R3 — Indication scope mismatch

## Rule

If the trial's primary expansion indication or accrual focus is NOT the patient's cancer type, demote `match` → `conditional`. The patient may still be eligible for an "all-comers" or "other solid tumors" cohort, but the spot is competitive and the molecular biology may differ.

## Why this rule exists

Many basket trials enroll "advanced solid tumors with KRAS G12C mutation" but the dose-expansion phase or the published interim data focus on a specific tumor type (typically NSCLC, since that's where KRAS G12C inhibitors have the strongest data). A CRC patient who matches by mutation but enters the "other solid tumors" cohort may face:

- Lower priority for screening slots
- Less mature efficacy data for their tumor type
- Smaller cohort → less statistical confidence

R3 surfaces this so the patient's clinical team can weigh it.

## How to apply

Read the trial's:
1. **Title** — does it mention a specific cancer (e.g. "KRAS G12C-Mutated NSCLC") or is it pan-tumor ("Advanced Solid Tumors")?
2. **Primary outcome** — usually phrases like "ORR in NSCLC cohort" reveal the priority indication
3. **Cohort structure** in eligibility — explicit cohorts by tumor type
4. **Sponsor program emphasis** — most KRAS G12C programs (sotorasib, adagrasib) led with NSCLC then expanded to CRC; the Phase 2 expansions usually reflect that

## Decision

```
patient.cancer_type = X

if trial is single-tumor for X: ✅ no R3
if trial is pan-tumor / basket AND X is named in expansion cohorts: ✅ no R3
if trial is pan-tumor AND X is in "other solid tumors" cohort only: R3 → conditional
if trial is single-tumor for Y (Y ≠ X): R3-hard → exclude
```

## Examples

- NCT07209111 (Calderasib MK-1084 advanced solid tumors): basket, with explicit cohorts for CRC, NSCLC, pancreatic — for a CRC patient, **no R3 trigger** (CRC is a named cohort)
- A trial titled "Sotorasib + Cetuximab in BRAF V600E Colorectal Cancer" — for a CRC patient with KRAS G12C (no BRAF V600E), R3-hard → exclude (wrong molecular cohort, even though same tumor type)
- A trial enrolling "any KRAS-mutant solid tumor" with Phase 2 expansion only in pancreatic — for a CRC patient, R3 → conditional

## Output marker

```json
{
  "hard_rules_triggered": ["R3"],
  "R3_detail": {
    "patient_cancer_type": "CRC",
    "trial_primary_indication": "NSCLC + pancreatic",
    "trial_includes_patient_cancer_in_cohort": true,
    "patient_cohort_priority": "low|medium|high"
  }
}
```
