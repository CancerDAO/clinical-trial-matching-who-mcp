# R1 — Prior same-class drug exclusion

## Rule

If the trial's exclusion criteria explicitly bar prior exposure to a drug class, AND the patient has received any drug in that class, demote the verdict from `match` to `conditional` (NOT `exclude` — the patient may still be eligible for a different cohort, or the exclusion may be waived after washout).

## Why this rule exists

In v1.7.x this was a Python regex (`prior_kras_inhibitor_excluded` boolean in `scoring/gating.py`). It silently failed on:

- Trials excluding "prior immune checkpoint inhibitor" — regex looked for "PD-1" string, missed broader phrasing
- Trials excluding "any prior anti-angiogenic therapy" — regex didn't enumerate VEGFR-TKIs (apatinib, regorafenib, fruquintinib)
- Trials excluding "prior treatment with a KRAS inhibitor" — regex was hardcoded to G12C-specific phrasing

Result: patients with prior camrelizumab (anti-PD-1) and bevacizumab + apatinib (anti-VEGF + VEGFR-TKI) were matched to trials that explicitly excluded those classes, with zero R1 demotion.

## Drug class reference

Use the `therapy_classes` map in `skills/clinical-trial-matching/data/clinical_ontology.json`. Key classes for CRC patients:

| Class | Common drugs | Common exclusion phrasings |
|---|---|---|
| anti-PD-1 | pembrolizumab, nivolumab, camrelizumab, tislelizumab, sintilimab, toripalimab | "prior immune checkpoint inhibitor", "prior anti-PD-1/PD-L1", "previous treatment with a PD-1/PD-L1 inhibitor" |
| anti-PD-L1 | atezolizumab, durvalumab, avelumab | (often grouped with anti-PD-1) |
| anti-VEGF | bevacizumab, ramucirumab, ziv-aflibercept | "prior anti-angiogenic therapy", "prior VEGF-targeted treatment", "prior bevacizumab" |
| VEGFR-TKI | apatinib, regorafenib, fruquintinib, anlotinib, lenvatinib | "prior VEGFR tyrosine kinase inhibitor", "prior multi-kinase inhibitor targeting VEGFR" |
| KRAS G12C inhibitor | sotorasib, adagrasib, divarasib, glecirasib, MK-1084, D3S-001, PF-07934040, JAB-21822 | "prior treatment with a KRAS-directed therapy", "prior KRAS G12C inhibitor", "prior treatment with a covalent KRAS inhibitor" |
| KRAS G12D inhibitor | MRTX1133, GFH375, RMC-9805, ASP3082, JYP0015 | "prior treatment with a KRAS G12D inhibitor", "prior treatment with a non-covalent KRAS inhibitor" |
| pan-RAS / RAS-ON | RMC-6236, RMC-6291, BI-1701963 | "prior treatment with a pan-RAS inhibitor", "prior RAS(ON) inhibitor" |
| EGFR-TKI | osimertinib, gefitinib, erlotinib, icotinib, afatinib, dacomitinib, lazertinib | "prior EGFR-TKI" — usually NSCLC-specific |
| anti-EGFR mAb | cetuximab, panitumumab | "prior anti-EGFR antibody", "prior cetuximab/panitumumab" |

## How to apply

For each exclusion criterion in the trial:

1. Identify the drug class being excluded (be permissive — "prior immunotherapy" usually means any anti-PD-1/PD-L1/CTLA-4)
2. Look up the class in `therapy_classes`
3. Cross-reference with `patient.prior_therapies` (drug names) and `patient.treatment_history[*].regimen` (regimen names)
4. If overlap found, mark this exclusion as `❌ 触发排除` in the per-criterion table, AND set the trial-level R1_triggered flag

## Edge cases

- **Concurrent therapy that's about to stop**: if patient is currently on a class-overlapping drug but planning to stop, treat as triggering R1 (washout will be required, screening eligibility decision is the trial's call).
- **Brief exposure that didn't cause progression**: still triggers R1. Some trials have nuanced exclusions ("≥3 cycles required") — capture in the criterion-level evaluation, but R1 still fires for the screening conversation.
- **Same drug class but different mechanism (e.g. nivolumab vs camrelizumab)**: both anti-PD-1 → R1 fires.
- **G12C vs G12D inhibitors**: different classes. Patient who received G12D drug does NOT trigger R1 for a G12C trial (but may still face an "any prior KRAS-directed therapy" exclusion — read the actual phrasing).

## Output marker

In the per-trial JSON, set:
```json
{
  "hard_rules_triggered": ["R1"],
  "R1_detail": {
    "excluded_class": "anti-PD-1",
    "patient_drugs_in_class": ["camrelizumab"],
    "exclusion_text": "..."
  }
}
```
