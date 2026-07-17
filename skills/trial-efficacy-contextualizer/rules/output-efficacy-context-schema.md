# trial-efficacy-contextualizer output schema

```json
{
  "trial_id": "NCT07209111",

  "efficacy_snapshot": {
    "match_type": "trial_specific | mutation_class_baseline | drug_class_baseline | drug_class_baseline_other_cancer | no_data",
    "metrics": {
      "expected_orr": 0.26,
      "expected_orr_range": "20-30%",
      "expected_pfs_months": 5.6,
      "expected_pfs_range": "4-7mo",
      "expected_dor_months": null,
      "expected_os_months": null
    },
    "evidence_source": {
      "tier": "phase_3_rct | phase_2_published | mutation_class_baseline | drug_class_baseline | etc",
      "citation": "Author et al. Journal Year (PMID) or NCTID readout description",
      "n": 53,
      "patient_population_described": "2L+ KRAS G12C mCRC (n=53), median 3 prior lines"
    },
    "applies_because": "REQUIRED — explain why this evidence applies to THIS patient",
    "caveats": [
      "list of important caveats",
      "e.g. 'Trial uses different drug in same class'",
      "e.g. 'Patient differs from trial population in X way'"
    ]
  },

  "vs_soc": {
    "available": true,
    "patient_line_context": "L4 mCRC KRAS G12C MSS, post-FOLFOX/KELOX/Camrelizumab/Apatinib",
    "soc_options": [
      {
        "regimen": "string",
        "expected_orr": 0.26,
        "expected_orr_range": "string",
        "expected_pfs_months": 5.6,
        "expected_dor_months": null,
        "expected_os_months": 11.9,
        "evidence": "trial / publication name",
        "patient_eligibility_note": "any reason patient may NOT be eligible for this SoC"
      }
    ],
    "head_to_head_summary": "1-3 sentence narrative comparing trial vs SoC options"
  },

  "redundancy_with_existing_options": {
    "is_trial_redundant_with_approved_combo": false,
    "explanation": "If trial intervention is mechanistically identical to an FDA-approved combo the patient could access off-trial, flag here"
  }
}
```

## Required fields

- `applies_because` in efficacy_snapshot — REQUIRED to prevent class-baseline mismatches like the v1.7.x JYP0015 bug
- `evidence_source.tier` — must be one of the enumerated tiers; downstream synthesis uses tier for confidence weighting
- `vs_soc.head_to_head_summary` — REQUIRED when `vs_soc.available = true`; do not emit empty
- `redundancy_with_existing_options` — flags when patient could just access an approved combo off-trial (e.g. CRC KRAS G12C trial when sotorasib+panitumumab is FDA-approved and accessible)

## When data unavailable

```json
{
  "trial_id": "NCT...",
  "efficacy_snapshot": {
    "match_type": "no_data",
    "metrics": null,
    "evidence_source": null,
    "applies_because": "No published efficacy data for this drug + this cancer type + this patient's mutation. Trial is first-in-class / first-in-disease.",
    "caveats": ["Counsel patient that response is unpredictable; ask sponsor for any unpublished interim safety data"]
  },
  "vs_soc": {
    "available": true,
    "patient_line_context": "...",
    "soc_options": [...],
    "head_to_head_summary": "Trial response unpredictable (no class data); SoC options have known modest activity (ORR <10%)."
  }
}
```

Honest "no data" beats fabricated estimates.

## Required development evidence for non-excluded trials

The efficacy_context object must also contain development_evidence and evidence_search. Every evidence item requires evidence_stage, citation, URL, population or model, findings, patient applicability, and limitations. The search record requires found or no_relevant_publication status, ISO-8601 search time, exact queries, and a patient-facing summary.

Match and conditional trials require this search record. no_relevant_publication is valid and preferable to inventing evidence. Excluded trials do not require deep literature retrieval.
