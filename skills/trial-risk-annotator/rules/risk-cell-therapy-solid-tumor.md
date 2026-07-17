# Risk profile: Cell therapy in solid tumors

Covers CAR-T, TIL (tumor infiltrating lymphocyte), TCR-T (T-cell receptor engineered), CIK / DC-CIK, and engineered NK therapies for solid tumors. **Distinct from hematologic CAR-T** — solid tumor cell therapy is much earlier in clinical development with different efficacy/safety profile.

## Universal cautions for solid tumor cell therapy

- **Efficacy gap**: solid tumor cell therapy ORR typically 10–30%, vastly lower than hematologic CAR-T (60–90% in ALL/DLBCL)
- **Failure modes**: target antigen heterogeneity + antigen escape; tumor microenvironment immunosuppression; inadequate trafficking to tumor site
- **Logistics**: 4–8 week manufacture window between leukapheresis and infusion — patient must have stable disease through this period or have salvage chemo available
- **Center requirements**: ICU + CRS management capability required; not all hospitals can host
- **Manufacture failure rate**: 5–15% (low lymphocyte count, T-cell dysfunction, viral contamination of starting product)

## CAR-T (CEA, GUCY2C, MUC1, Claudin18.2)

- **CRC-relevant targets**: CEA (most common), GUCY2C, KRAS-G12V/G12D peptide-MHC (rare)
- **Published CRC data**: CEA CAR-T trials have ORR 0–25% in heavily pretreated mCRC; durability typically <6 months
- **Major AEs**: CRS (mild for solid tumor, usually grade 1–2 since lower disease burden), neurotoxicity rare, on-target/off-tumor toxicity (CEA expressed in normal GI mucosa → diarrhea, colitis)
- **Patient screening**: ALC (absolute lymphocyte count) ≥0.5 × 10⁹/L recommended for adequate apheresis yield
- **CRC-specific note**: CEA expression heterogeneity is high — trial may require IHC ≥2+ confirmation. Patient's archival tissue or fresh biopsy needed.

## TIL (tumor-infiltrating lymphocyte)

- **Efficacy in solid tumor**: established in melanoma (lifileucel, ORR ~30%); emerging data in NSCLC, HNSCC, cervical
- **CRC**: limited data; mostly research-grade trials. Best response to TIL correlates with high TMB and neoantigen load — patient's TMB 7.7 muts/Mb is borderline (TMB-H usually defined as ≥10).
- **Manufacture**: requires fresh tumor tissue, surgical or core biopsy of accessible lesion. Outpatient manufacture not yet routine in China.

## TCR-T (T-cell receptor)

- **Targets**: NY-ESO-1, MAGE-A4, KRAS G12V (Adaptimmune, IOVA), KRAS G12D (NCI Rosenberg group)
- **HLA restriction**: ALL TCR-T require specific HLA haplotype (most commonly HLA-A*02:01). Patient must be HLA-typed before screening; if not typed, ❓ blocker, list in action items.
- **Efficacy**: emerging — Rosenberg KRAS G12D TIL/TCR-T case report shows durable response, but in <20 patients total
- **CRC patient-specific**: KRAS G12C TCR-T is pre-clinical; KRAS G12D TCR-T (NCI) is for KRAS G12D patients only. **Don't suggest KRAS G12D TCR-T to a KRAS G12C patient** (mutation-specific peptide-HLA targeting).

## CIK / DC-CIK / immune cell mixtures

- **Evidence quality (2026)**: substantially weaker than CAR-T or TIL. Most data is single-arm Chinese studies with selection bias.
- **Clinical positioning**: typically combined with chemo or anti-angiogenics; mechanism of added benefit unclear (some claim immune priming, others claim no benefit beyond placebo)
- **Risk note**: low AE profile, but evidence-based clinical benefit is uncertain. If patient asks, frame transparently: "this is exploratory; the chemo/regorafenib backbone is doing most of the work in the trial."
- **Trial example**: NCT07343791 "DC-CIK + Epaloliposide + Vortexil + Regorafenib 3L" — bulk of clinical activity is from regorafenib, not the DC-CIK component.

## Phase 1 dose-escalation overlay

If the cell therapy trial is Phase 1 dose escalation:
- Add `risk-phase-1-dose-escalation` risk
- Note that early cohorts may receive sub-therapeutic doses
- Recommend patient ask sponsor whether Phase 1b expansion (recommended dose) is open, not just Phase 1a escalation

## Output template (CRC patient on CEA CAR-T)

```json
{
  "key": "car_t_solid_tumor_crc",
  "mechanism": "CEA-targeted CAR-T",
  "cancer_context": "CRC",
  "risk_level": "high_uncertainty",
  "narrative": [
    "Solid tumor CAR-T ORR 10-30% in mCRC; durability typically <6 months",
    "CEA expression heterogeneity → confirm IHC ≥2+ before screening",
    "On-target/off-tumor toxicity: CEA in normal GI mucosa → diarrhea, possible colitis",
    "Manufacture window 4-8 weeks → ensure salvage option available during this gap",
    "ALC ≥ 0.5 × 10⁹/L required for apheresis — verify recent CBC"
  ]
}
```
