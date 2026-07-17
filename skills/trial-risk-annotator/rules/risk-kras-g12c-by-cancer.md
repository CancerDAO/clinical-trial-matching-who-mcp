# Risk profile: KRAS G12C inhibitor by cancer type

KRAS G12C covalent inhibitors (sotorasib, adagrasib, divarasib, glecirasib, fulzerasib, garsorasib, olomorasib, calderasib/MK-1084, D3S-001, PF-07934040, JAB-21822, BGB-53038, GDC-6036) have **markedly different efficacy and risk profiles depending on the tumor type**. Risks below MUST be filtered to the patient's cancer type.

## NSCLC (KRAS G12C)

- **Monotherapy ORR**: ~30–40% (sotorasib CodeBreaK 100; adagrasib KRYSTAL-1)
- **Median PFS**: ~6 months
- **Class AEs**: GI (nausea, diarrhea), hepatic transaminase elevation, fatigue. Mostly grade 1–2 and reversible.
- **Resistance**: emerges in 6–12 months; mechanisms include secondary KRAS mutations (Y96D, R68S), MET amplification, NF1 loss, EMT, lineage switch
- **Combination paradigm**: + anti-PD-1 increases hepatic AE significantly (don't pair if patient already on or recently on PD-1)

## Colorectal (KRAS G12C) — DIFFERENT from NSCLC

- **Monotherapy ORR**: ~10% (substantially lower than NSCLC) due to **adaptive EGFR feedback** unique to CRC biology
- **Combination with anti-EGFR mAb (cetuximab or panitumumab) is the standard paradigm**:
  - CodeBreaK 300: sotorasib + panitumumab vs investigator choice → ORR 26%, mPFS 5.6mo (vs 0% / 2.2mo for chemo)
  - KRYSTAL-10: adagrasib + cetuximab → ORR ~46% in 2L+ KRAS G12C mCRC
- **Risk pattern**: skin toxicity (acneiform rash from anti-EGFR), hypomagnesemia, paronychia. KRAS G12C class AE is mild.
- **R1 alert**: many CRC trials EXCLUDE patients with prior anti-EGFR therapy. Verify patient hasn't received cetuximab/panitumumab.
- **Patient-specific note for CRC patients**: if the trial is monotherapy, expect lower ORR than NSCLC literature suggests. Combo arms or post-monotherapy progressors going to combo are the more clinically meaningful paths.

## Pancreatic (KRAS G12C — rare, ~1-2% of PDAC)

- **Monotherapy ORR**: ~20% (sotorasib in CodeBreaK 100 PDAC cohort)
- **PFS**: short (~4 months) due to PDAC's aggressive natural history
- **Combination with chemo (FOLFIRINOX/AG)**: very limited data
- **Risk pattern**: same class AEs as NSCLC; PDAC patients often have hepatic dysfunction baseline so transaminase elevation should be monitored carefully
- **Patient-specific note**: KRAS G12D is the dominant PDAC mutation (~40%); G12C in PDAC is rare and KRAS G12D drugs are NOT cross-active. Don't transfer G12D efficacy data to G12C patients (or vice versa).

## Other solid tumors (basket trials)

For patients enrolled in pan-tumor basket cohorts (cholangiocarcinoma, gastric, biliary tract, etc.):
- Efficacy data is sparse — usually single-digit patient counts in published interim
- Risk pattern is class-typical (GI, hepatic, fatigue)
- Counsel patient that the data supporting the trial is mostly NSCLC + CRC; outcomes for other tumors are exploratory

## DO NOT emit (avoid these v1.7.x bug patterns)

- ❌ "在 PDAC 中作为 KRAS G12D 抑制剂联合伙伴" — this is a PDAC-specific narrative; do not attach to CRC patients
- ❌ "EGFR antibody combination (PDAC)" risk key — CRC has its own EGFR combo paradigm (cetuximab/panitumumab); the PDAC narrative is irrelevant
- ❌ Quoting NSCLC ORR (~30-40%) for a CRC patient as the expected response

## Output template (CRC patient on KRAS G12C trial)

```json
{
  "key": "kras_g12c_crc",
  "mechanism": "KRAS G12C covalent inhibitor",
  "cancer_context": "CRC",
  "risk_level": "moderate",
  "narrative": [
    "CRC monotherapy ORR ~10% (vs ~30% in NSCLC) due to adaptive EGFR feedback specific to CRC",
    "If trial includes anti-EGFR combo (cetuximab/panitumumab), expect ORR ~26-46% per CodeBreaK 300 / KRYSTAL-10",
    "Class AE: GI, hepatic transaminase elevation, fatigue — mostly grade 1-2",
    "R1 check: many CRC trials exclude prior anti-EGFR — verify patient's regimen history"
  ]
}
```
