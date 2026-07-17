# Risk profile: pan-RAS / RAS-ON inhibitors

Drugs in class: RMC-6236 (Revolution Medicines, daraxonrasib), RMC-6291 (G12C-selective ON-state), BI-1701963 (SOS1 inhibitor — different mechanism, often grouped).

## Mechanism

"RAS-ON" inhibitors bind RAS in its active GTP-bound state via tri-complex with cyclophilin A. Cover multiple KRAS variants (G12D, G12V, G12X) plus some HRAS/NRAS. Mechanistically distinct from G12C covalent (off-state) inhibitors.

## Why this matters for the patient

For a patient who has progressed on a G12C off-state inhibitor (sotorasib, adagrasib, glecirasib, etc.), pan-RAS / RAS-ON inhibitors are a logical next step — they may overcome class-specific resistance mutations (Y96D, R68S) that escape covalent G12C drugs.

## Published efficacy (early)

- **RMC-6236 (daraxonrasib)** in PDAC: Phase 1 ORR ~20–30%, mPFS ~7 mo
- **RMC-6236** in NSCLC G12X: ORR ~38%, mPFS ~10 mo
- **RMC-6236** in CRC: limited data, but expected lower than NSCLC by analogy to G12C class
- **RMC-6291** in NSCLC G12C: ORR ~40%

## Risk pattern

- GI (nausea, vomiting, diarrhea) — class-typical
- Hepatic transaminase elevation
- Cyclophilin A binding has been associated with renal effects in animal models — monitor BUN/Cr
- Phase 1 dose escalation overlay applies (sub-therapeutic early doses)

## Cross-tumor caution

Same as G12C class — efficacy is highly cancer-type dependent. CRC patients should not be counseled with NSCLC ORR.

## R1 interaction

If patient previously received a G12C off-state inhibitor (sotorasib, adagrasib, etc.), some pan-RAS trials accept that exposure (different class, different binding pocket); others exclude it. Read trial eligibility carefully — this is exactly where the R1 hard rule needs LLM judgment, not regex.

## Output template (CRC patient)

```json
{
  "key": "pan_ras_crc",
  "mechanism": "Pan-RAS / RAS-ON inhibitor",
  "cancer_context": "CRC",
  "risk_level": "moderate",
  "narrative": [
    "RAS-ON binding distinct from G12C off-state inhibitors — may overcome class resistance",
    "CRC efficacy data limited; expect lower ORR than NSCLC by analogy (CRC ~10-15% vs NSCLC ~40%)",
    "Class AEs: GI, hepatic, monitor renal function (cyclophilin A binding mechanism)",
    "Phase 1 dose escalation: ask sponsor whether RP2D cohort is open"
  ]
}
```
