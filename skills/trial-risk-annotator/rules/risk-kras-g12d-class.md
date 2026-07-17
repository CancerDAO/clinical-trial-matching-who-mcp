# Risk profile: KRAS G12D inhibitor

Drugs in class: MRTX1133 (Mirati), GFH375 / fortemastinib (innotech), RMC-9805 (Revolution Medicines), ASP3082 (Astellas), JYP0015 (Joyo Pharma).

## Cancer-type specificity (CRITICAL)

KRAS G12D drug-class baselines come almost entirely from **PDAC** patient cohorts (where G12D is the dominant mutation, ~40% of PDAC). Do NOT apply these baselines to:

- **KRAS G12C patients** — different drug class, no cross-activity
- **CRC patients with KRAS G12D** — limited data, may differ from PDAC due to tissue-specific feedback (not enough published data to know)
- **NSCLC patients with KRAS G12D** — almost no data

## Published efficacy (PDAC, G12D)

- **MRTX1133**: preclinical strong, early Phase 1 ORR ~30-40%
- **GFH375**: ESMO 2025 readout — n=66 KRAS G12D PDAC, ORR ~40%, mPFS ~5.5 mo
- **RMC-9805**: Phase 1 multi-tumor, data immature
- Class baseline (PDAC): expected ORR 20–40%, mPFS 3–6 months

## Risk pattern

- GI: nausea, diarrhea (often dose-limiting)
- Skin rash
- Fatigue
- Mostly grade 1–2

## Pan-RAS overlap (R5 alert for trial-gater)

Some "KRAS G12D inhibitor" trials actually accept broader RAS mutations at codon 12 (G12C, G12V, G12A, G12S, G12R) or even codon 13. Read the actual eligibility — examples:

- **NCT06895031 (JYP0015)**: trial accepts ALL codon 12, 13, 61, 117, 146 RAS mutations across KRAS/NRAS/HRAS — NOT G12D-specific despite the drug being marketed as a G12D inhibitor
- This means a G12C patient may be ELIGIBLE but the drug's published data (G12D PDAC) is NOT predictive of their response

## v1.7.x bug to avoid

In v1.7.x, the efficacy_lookup.py applied "KRAS G12D inhibitor (small molecule)" class baseline to NCT06895031 even though the trial covers G12C. The patient (KRAS G12C mCRC) saw "expected ORR 30%, mPFS 4.5 months" in their report — those numbers are PDAC G12D, irrelevant to a G12C CRC patient.

**v2 rule**: if the trial enrolls multiple RAS variants and the drug class baseline is from G12D PDAC, the efficacy contextualizer must NOT apply the G12D baseline to non-G12D patients. Either:

1. Mark efficacy as "no class-relevant baseline available; await trial-specific readout"
2. Or pull the patient's mutation-specific class baseline (G12C class for G12C patients)

## Output template (G12C patient looking at JYP0015 / similar pan-codon-12 RAS trial)

```json
{
  "key": "kras_g12d_drug_pan_codon_eligibility_g12c_patient",
  "mechanism": "KRAS G12D inhibitor (broader RAS eligibility)",
  "cancer_context": "CRC",
  "risk_level": "high_uncertainty",
  "narrative": [
    "Drug is marketed as KRAS G12D inhibitor; trial accepts broader codon 12/13/61 RAS variants including patient's G12C",
    "Published drug-class data is from G12D PDAC patients — NOT predictive of G12C activity",
    "If patient is enrolled, response data will be exploratory; do NOT counsel patient using G12D PDAC ORR (~40%)",
    "Consider asking sponsor whether G12C-specific cohort exists or if trial captures cohort-level analysis"
  ]
}
```
