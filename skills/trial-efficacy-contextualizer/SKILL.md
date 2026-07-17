---
name: trial-efficacy-contextualizer
description: Use when contextualizing a clinical trial's expected efficacy and comparing against current standard-of-care for the patient's cancer type and treatment line. Triggers when the parent clinical-trial-matching skill needs efficacy snapshots and vs-SoC head-to-head data per decision path. Replaces v1.7.x efficacy_lookup.py + efficacy_database.json + soc_benchmarks.json (which had only 1 CRC SoC entry, leaving most CRC patients with "vs SoC: not available" in their report).
license: MIT
metadata:
  author: CancerDAO
  version: "2.0.0"
  parent_skill: clinical-trial-matching
---

# trial-efficacy-contextualizer

You generate two things per trial:

1. **Efficacy snapshot** — best-available estimate of the trial's expected ORR/PFS/DoR for THIS patient's cancer type and mutation context
2. **vs-SoC head-to-head** — comparison against the patient's current standard-of-care option at this treatment line

## The bug this subskill exists to fix

v1.7.x had `efficacy_database.json` (NCT-level + drug-class baselines) and `soc_benchmarks.json` (cancer × line × molecular subtype). Two failure modes:

1. **CRC SoC table had only 1 entry** (`metastatic_1L_BRAF_V600E`). Every other CRC patient (the vast majority) saw `"vs_soc": {"available": false}` in their report. This is the modal case for CRC — no SoC comparison was ever shown.
2. **Class baselines applied without mutation gating**. NCT06895031 (JYP0015) was tagged "KRAS G12D inhibitor (small molecule)" with G12D PDAC ORR 30%, mPFS 4.5mo applied to a KRAS G12C CRC patient. Nonsensical and misleading.

v2: every efficacy claim must name (cancer × mutation × line) explicitly and either pull a defensible source or admit "no published data for this combination".

## Inputs

```json
{
  "trial": {
    "id": "NCT...",
    "title": "...",
    "phases": [...],
    "interventions": [...],
    "mechanism_of_action": "..."
  },
  "patient": { /* full patient.json */ },
  "patient_current_line_for_efficacy_purposes": <int>
}
```

## Output

```json
{
  "trial_id": "NCT07209111",
  "efficacy_snapshot": {
    "match_type": "trial_specific | mutation_class_baseline | drug_class_baseline | no_data",
    "metrics": {
      "expected_orr": 0.26,
      "expected_orr_range": "20-30%",
      "expected_pfs_months": 5.6,
      "expected_pfs_range": "4-7mo",
      "expected_dor_months": null
    },
    "evidence_source": {
      "citation": "CodeBreaK 300 (sotorasib + panitumumab vs investigator choice in 2L+ KRAS G12C mCRC) — Yaeger NEJM 2024",
      "tier": "phase_3_rct"
    },
    "applies_because": "Trial intervention is KRAS G12C inhibitor + anti-EGFR mAb; patient is KRAS G12C mCRC 2L+ — directly analogous to CodeBreaK 300 patient population",
    "caveats": [
      "CodeBreaK 300 used sotorasib + panitumumab; this trial uses calderasib (MK-1084) — same class, same combination paradigm, but trial-specific data not yet published",
      "Patient was on prior anti-VEGF (bevacizumab) but not anti-EGFR — eligibility for the cetuximab/panitumumab arm should be straightforward"
    ]
  },
  "vs_soc": {
    "available": true,
    "patient_line_context": "L4 mCRC KRAS G12C, MSS, post-FOLFOX/KELOX/Camrelizumab/Apatinib",
    "soc_options": [
      {
        "regimen": "regorafenib monotherapy",
        "expected_orr": 0.01,
        "expected_orr_range": "<5%",
        "expected_pfs_months": 1.9,
        "evidence": "CORRECT trial — regorafenib in chemo-refractory mCRC"
      },
      {
        "regimen": "TAS-102 + bevacizumab",
        "expected_orr": 0.06,
        "expected_orr_range": "5-10%",
        "expected_pfs_months": 5.6,
        "evidence": "SUNLIGHT trial — TAS-102 + bev vs TAS-102 in 3L mCRC"
      },
      {
        "regimen": "fruquintinib monotherapy",
        "expected_orr": 0.02,
        "expected_orr_range": "1-5%",
        "expected_pfs_months": 3.7,
        "evidence": "FRESCO-2 trial — fruquintinib in chemo-refractory mCRC"
      },
      {
        "regimen": "sotorasib + panitumumab (FDA approved 2024 for KRAS G12C mCRC 2L+)",
        "expected_orr": 0.26,
        "expected_orr_range": "20-30%",
        "expected_pfs_months": 5.6,
        "evidence": "CodeBreaK 300",
        "patient_eligibility_note": "Patient has prior bevacizumab but not cetuximab/panitumumab — eligible for this approved combo"
      }
    ],
    "head_to_head_summary": "Trial expected ORR (~26-30%) is competitive with FDA-approved sotorasib+panitumumab combo (ORR 26%); both substantially outperform regorafenib/TAS-102/fruquintinib (ORR 1-6%). Patient should weigh trial vs FDA-approved combo (which has known data, established reimbursement pathway, and may be available without trial enrollment delay)."
  }
}
```

## Process

```
1. Identify trial mechanism + intervention combo
2. Determine patient's effective treatment line and prior therapy classes
3. Search for trial-specific published data (CT.gov citations, recent ASCO/ESMO readouts)
4. If trial-specific data unavailable, find the most-relevant published analog:
   a. Same drug + same cancer + same line → trial_specific match
   b. Same drug + different line → mutation_class_baseline (note caveat)
   c. Same class + same cancer → drug_class_baseline (cancer-specific!)
   d. Same class + different cancer → DO NOT use unless explicitly noted as exploratory
5. List patient's SoC options at current line — use your training knowledge of the cancer's published guidelines (NCCN / CSCO / ESMO) and pivotal trial data
6. Compose head-to-head comparison
```

## Tier hierarchy for evidence

| Tier | Description | Use |
|---|---|---|
| `trial_specific_phase_3` | This exact trial has Phase 3 readout | Highest confidence |
| `trial_specific_phase_2` | This exact trial has Phase 2 interim/final | High confidence |
| `phase_3_rct` | Phase 3 in same drug + same indication | Strong analog |
| `phase_2_published` | Phase 2 in same drug + same indication | Moderate analog |
| `mutation_class_baseline` | Pooled data for same drug class + same mutation + same cancer | Acceptable; flag as "class estimate" |
| `drug_class_baseline_other_cancer` | Same class, different cancer | Use ONLY with explicit cross-cancer caveat |
| `no_data` | No published analog | Honest "no data" — do not invent estimates |

## SoC knowledge source

For the patient's cancer + treatment line, list the relevant SoC options from your training knowledge of NCCN / CSCO / ESMO guidelines and pivotal trials. Prioritize:

- **Approved combos for the patient's molecular subtype first** (e.g. for KRAS G12C mCRC 2L+: sotorasib + panitumumab per CodeBreaK 300, FDA approved 2024)
- **Standard chemo-refractory options** (e.g. for 3L mCRC: regorafenib / TAS-102 ± bevacizumab / fruquintinib)
- **Cancer-specific recent additions** (post-2024 pivotal trial readouts)

Cite trial names + key metrics (ORR, mPFS, mOS) — your output is consumed by downstream synthesis that will surface these to clinicians, who will check citations.

The repo previously shipped per-cancer SoC reference files (`soc-crc-by-line.md` etc.) — these were removed because the LLM has this knowledge in training and the files added maintenance burden without accuracy benefit. If a clinician requests citation lock-in for reproducibility, the user can re-introduce per-cancer SoC rule files.

## Output

- [Output schema](rules/output-efficacy-context-schema.md)

## Mandatory grounding

Before emitting any efficacy number, verify:

1. ✅ The metric comes from a population matching patient (cancer + mutation + line)
2. ✅ The drug class matches the trial's actual intervention (G12D class data ≠ G12C trial)
3. ✅ The citation is a real, locatable source (paper, registry entry, FDA label)
4. ✅ If you're using a class baseline, the class is the RIGHT class for this patient's mutation

If any check fails, emit `"match_type": "no_data"` rather than fabricating.

## Development evidence chain

For every trial whose gating verdict is match or conditional, perform a publication search before producing the efficacy snapshot. Do not assume that a recruiting drug necessarily has a published paper: first-in-human programs may rely on unpublished sponsor packages, conference abstracts, patents, or class evidence.

Emit development_evidence plus evidence_search. Every evidence item must include evidence stage, citation, resolvable URL, findings, patient applicability, and limitations. A registry page or sponsor press release may be shown as supporting material but must not be labeled as a peer-reviewed paper. Cross-cancer or preclinical findings must never be converted into an expected patient response rate.
