# Risk profile: KRAS G12C inhibitor by cancer type

## Evidence attribution

Never source a numeric efficacy estimate from this rule. Bind every estimate
to a grounded publication candidate and preserve its named study, cohort,
analysis date, endpoint definition, and uncertainty. KRYSTAL-1 and KRYSTAL-10
are distinct studies and must not be interchanged.

KRAS G12C covalent inhibitors (sotorasib, adagrasib, divarasib, glecirasib, fulzerasib, garsorasib, olomorasib, calderasib/MK-1084, D3S-001, PF-07934040, JAB-21822, BGB-53038, GDC-6036) have **markedly different efficacy and risk profiles depending on the tumor type**. Risks below MUST be filtered to the patient's cancer type.

## NSCLC (KRAS G12C)

- **Monotherapy activity**: established in previously treated KRAS G12C NSCLC; use the grounded evidence packet for current estimates
- **Class AEs**: GI (nausea, diarrhea), hepatic transaminase elevation, fatigue. Mostly grade 1–2 and reversible.
- **Resistance**: acquired resistance can involve secondary KRAS changes, bypass-pathway activation, EMT, or lineage change
- **Combination paradigm**: + anti-PD-1 increases hepatic AE significantly (don't pair if patient already on or recently on PD-1)

## Colorectal (KRAS G12C) — DIFFERENT from NSCLC

- **Monotherapy activity**: generally lower than in NSCLC because adaptive EGFR feedback is important in CRC biology
- **Combination with anti-EGFR mAb (cetuximab or panitumumab) is the standard paradigm**:
  - use the grounded evidence packet to describe the relevant agent, combination, cohort, comparator, and endpoint
- **Risk pattern**: skin toxicity (acneiform rash from anti-EGFR), hypomagnesemia, paronychia. KRAS G12C class AE is mild.
- **R1 alert**: many CRC trials EXCLUDE patients with prior anti-EGFR therapy. Verify patient hasn't received cetuximab/panitumumab.
- **Patient-specific note for CRC patients**: if the trial is monotherapy, expect lower ORR than NSCLC literature suggests. Combo arms or post-monotherapy progressors going to combo are the more clinically meaningful paths.

## Pancreatic (KRAS G12C — rare, ~1-2% of PDAC)

- **Monotherapy activity**: early cohort evidence exists, but estimates must come from the grounded evidence packet
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
    "CRC monotherapy activity is generally lower than in NSCLC because of adaptive EGFR feedback",
    "For an anti-EGFR combination, report only estimates present in the grounded evidence packet and name the exact study and cohort",
    "Class AE: GI, hepatic transaminase elevation, fatigue — mostly grade 1-2",
    "R1 check: many CRC trials exclude prior anti-EGFR — verify patient's regimen history"
  ]
}
```
