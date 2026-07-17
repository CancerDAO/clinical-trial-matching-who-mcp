# Diversity bucketing for Top-N decision paths

## Goal

Avoid emitting 3 paths that are all variants of the same drug class (e.g. 3 different KRAS G12C inhibitors). Patient and clinician benefit from seeing options across different mechanisms, regions, and modalities.

## Slots

Default N=3:

| Slot | Role | Selection criterion |
|---|---|---|
| 1 | `primary` | Highest composite score, China-accessible, non-Phase-1-only |
| 2 | `alternative_mechanism` OR `secondary` | Best path with a DIFFERENT drug class than slot 1 |
| 3 | `secondary_cell_therapy` OR `secondary_overseas` OR `secondary` | Best cell therapy OR best different-region path |

If a slot has no qualifying candidate, **leave the slot empty** rather than filling with a worse path just for diversity.

## Composite score formula

```
composite = 0.5 * feasibility_score
          + 0.3 * (1 - confidence_penalty_from_gating)
          + 0.2 * evidence_tier_weight
```

Where `evidence_tier_weight`:
- `trial_specific_phase_3` = 1.0
- `trial_specific_phase_2` = 0.9
- `phase_3_rct` = 0.85
- `phase_2_published` = 0.75
- `mutation_class_baseline` = 0.6
- `drug_class_baseline` = 0.45
- `drug_class_baseline_other_cancer` = 0.2
- `no_data` = 0.1

This formula intentionally weights feasibility (50%) over evidence (20%) — a Phase 3 trial in Boston with 0 China sites scores worse than a Phase 1 trial in Beijing with 11 China sites for a Chinese patient.

## Mechanism class tags (for diversity grouping)

Use the patient's mutation/biology to tag mechanisms:

- `kras_g12c_inhibitor`
- `kras_g12d_inhibitor`
- `pan_ras_inhibitor`
- `kras_inhibitor_combo_with_anti_egfr`
- `cell_therapy_car_t`
- `cell_therapy_til`
- `cell_therapy_tcr_t`
- `cell_therapy_cik_dc_cik`
- `bispecific_antibody`
- `adc` (antibody-drug conjugate)
- `chemo_combo` (chemotherapy backbone with novel partner)
- `immune_checkpoint_inhibitor`
- `radioconjugate`

Two paths with the same mechanism tag = same bucket (avoid both in Top 3).

## Anti-pattern: forcing diversity at the cost of fit

**Critical bug from v1.7.x**: the diversity bucketing forced a "secondary" slot to be filled with NCT06895031 (JYP0015, KRAS G12D drug applied to a G12C patient) just because it was the next-best "different mechanism". The drug was wrong for the patient.

**v2 rule**: when filling a diversity slot, the candidate MUST still pass these checks:

1. Trial mutation requirement matches patient mutation (or is mutation-agnostic)
2. Trial drug class is appropriate for patient mutation (G12C drugs for G12C patients; G12D drugs for G12D patients; pan-RAS / mutation-agnostic drugs OK for any RAS-mutant)
3. Patient has not already failed an equivalent regimen in the same drug class

If no candidate passes these checks for a diversity slot, leave the slot empty.

## Path-vs-path comparison narrative

For each chosen path, emit `alternatives_comparison`: 1-2 nearest similar trials NOT chosen, with explicit reason. This serves the "为什么选这条 ≠ 选 X / Y" block in the report.

```json
"alternatives_comparison": [
  {
    "trial_id": "NCT05410145",
    "trial_title": "D3S-001 mono/combo in KRAS G12C solid tumors",
    "reason_not_chosen": "feasibility 0.881 < 0.961 of chosen path; only 16 China sites vs chosen path's 11 — wait, 16 > 11. Re-evaluate. Actually D3S-001's 16 China sites is MORE — the choice should explain why the chosen path was preferred (e.g. trial-specific evidence tier higher for MK-1084 due to recent ESMO readout; or alternative composition/safety profile)."
  }
]
```

Note: this is one of the v1.7.x bugs — alternatives_comparison was sometimes self-contradicting. v2 must verify the comparison narrative is consistent with the metrics.

## Empty slot handling

```json
"decision_paths": [
  { ...slot 1 path... },
  { ...slot 2 path... },
  null  // no qualifying candidate for cell therapy / overseas slot
]
```

Or use length-2 array if N=3 was requested but only 2 qualifying. The HTML renderer should handle gracefully (don't show empty card).
