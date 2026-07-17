# R2 — Treatment line mismatch

## Rule

If the trial's treatment-line policy is incompatible with the patient's already-completed line count, demote:

- **R2-hard** (1L-only trial, patient is 2L+): demote to `exclude` — these patients cannot enroll regardless
- **R2-soft** (trial range narrower than patient's line, e.g. 2L–3L only, patient is 5L+): demote `match` → `conditional` — sponsor may waive on a case-by-case basis, especially if patient profile is otherwise rare

## Why this rule exists

v1.7.x had `treatment_line_policy` extracted by regex in `extraction/trial_metadata_extractor.py` looking for keywords like "first-line", "treatment-naïve". It missed:

- Trials phrased as "patients who have failed standard therapy" — line-agnostic, but regex assumed 2L+
- Trials with cohort-level line policies (e.g. "Cohort A: 1L; Cohort B: 2L+") — flattened to a single value

## Decision logic

```
patient.treatment_lines_completed = N
trial line policy = ?

if trial says "first-line only" / "treatment-naïve" / "no prior systemic":
    if N == 0: ✅ no R2
    if N >= 1: R2-hard → exclude

if trial says "≥1 prior line" / "post first-line" / "after FOLFOX/FOLFIRINOX":
    if N >= 1: ✅ no R2
    if N == 0: R2-hard → exclude (patient hasn't earned eligibility)

if trial says "2L–3L" or "second/third line":
    if N in {2, 3}: ✅ no R2
    if N == 1: R2-hard → exclude
    if N >= 4: R2-soft → conditional (sponsor may waive)

if trial says "any prior" / "previously treated" / no specific line:
    no R2

if trial is cohort-structured:
    evaluate per cohort; flag the cohort patient could fit
```

## Counting "lines completed"

A "line" generally means a distinct systemic regimen change. Count completed lines (excluding ongoing line):

- Adjuvant chemo after curative surgery — counts as 1 line if it was systemic
- Switch within same class (FOLFOX → FOLFIRI) — counts as a new line
- Adding a new drug to ongoing regimen (FOLFOX + bev → FOLFOX + cetuximab) — counts as a new line
- Maintenance after induction — same line
- Local therapy (radiation, surgery, ablation) without systemic change — does NOT count as a new systemic line

If `patient.current_therapy_ongoing == true`, the current ongoing therapy does NOT count toward `treatment_lines_completed`. The trial's eligibility evaluation should consider the patient's status at end-of-current-line for trials with washout requirements.

## Edge case: BRAF V600E mCRC

In CRC, BRAF V600E patients on encorafenib + cetuximab (BEACON regimen) — this is an approved 2L option. After progression, patient is "post-BEACON" and should be treated as 3L for trial purposes, even though the regimen change wasn't a traditional chemo switch.

## Output marker

```json
{
  "hard_rules_triggered": ["R2"],
  "R2_detail": {
    "trial_line_policy": "first-line only",
    "patient_lines_completed": 2,
    "severity": "hard|soft"
  }
}
```
