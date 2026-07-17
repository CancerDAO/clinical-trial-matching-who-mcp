# Goals-of-Care Trigger Logic

## The bug being fixed

v1.7.x `synthesis/goals_of_care.py` triggered GoC by comparing `patient.treatment_lines_completed` to ontology thresholds. For a CRC patient on L3 ongoing therapy, `treatment_lines_completed = 2` (L3 not yet completed), so the lookup compared against `2_post_second_line` threshold (9 months for CRC) and decided "9 > 6 → no trigger". Result: later-line metastatic CRC with substantial comorbidity got NO GoC discussion.

**v2 rule**: count the current ongoing line in trigger evaluation.

## Trigger conditions (any one fires)

### Trigger 1 — Line + cancer-type median OS

```
effective_line = patient.treatment_lines_completed
if patient.current_therapy_ongoing == true:
    effective_line += 1

cancer_ontology = clinical_ontology.cancers[patient.cancer_type]
median_os_at_line = cancer_ontology.median_os_months_at_line[f"{effective_line}_post_..."]
or fallback to cancer_ontology.median_os_months_at_line["3_plus"] if effective_line >= 3

threshold = cancer_ontology.goc_trigger_threshold_months  # default 6 months

if median_os_at_line <= threshold:
    trigger("Line + median OS")
```

For SYNTHETIC-CRC-LATER-LINE (CRC, treatment_lines_completed=2, current_therapy_ongoing=true):
- effective_line = 3
- CRC `3_plus` median OS per ontology = 6 months
- threshold = 6
- 6 <= 6 → TRIGGER ✅ (previously v1.7.x compared 9 against 6 → no trigger ❌)

### Trigger 2 — Rapid progression

```
last_regimen = patient.treatment_history[-1] (or [-2] if -1 is ongoing with positive response)
if last_regimen.outcome == "PD" AND last_regimen.cycles <= 4:
    trigger("Rapid progression on most recent line")
```

### Trigger 3 — Performance status

```
if patient.ecog >= 2 OR patient.kps <= 60:
    trigger("ECOG/KPS suggests limited treatment tolerance")
```

### Trigger 4 — Cumulative comorbidity burden

```
serious_comorbidities = count of items in patient.comorbidities matching:
  - cardiac (CAD, post-stent, HF, severe valve disease)
  - renal (eGFR < 60 baseline, CKD stage 3+, dialysis)
  - hepatic (cirrhosis, severe transaminase derangement, ascites)
  - active CNS disease (uncontrolled mets, prior stroke with residual deficit)
  - active second malignancy

if serious_comorbidities >= 3 OR any single life-limiting comorbidity (e.g. ESRD on HD, NYHA Class IV):
    trigger("Cumulative comorbidity burden constrains regimen tolerability")
```

For SYNTHETIC-CRC-LATER-LINE: three or more serious cardiac, renal, hepatic, or neurologic comorbidities → trigger ✅

### Trigger 5 — All-Phase-1 trial landscape

```
if all top decision paths are Phase 1 dose-escalation only:
    trigger("All best options are early-phase; counsel patient on uncertainty")
```

## Discussion recommendation framing

When triggered, emit a `discussion_recommendation` paragraph that:

1. States median OS at current line per cancer-type ontology (cite the source)
2. Frames the trial pathway as ONE option, not THE option
3. Lists alternatives explicitly: continued SoC (regorafenib/TAS-102/fruquintinib for CRC), best supportive care, hospice, comfort-focused care
4. Mentions trial logistics burden (cross-city travel, manufacture window for cell therapy, screening visits)
5. Avoids "推荐" / "should pursue" / "best option" language — uses "可选项" / "需讨论" / "权衡"

Example output for SYNTHETIC-CRC-LATER-LINE:

```
At L4 mCRC, median OS per published data is approximately 6 months (CRC ontology, sourced from CORRECT/RECOURSE/SUNLIGHT pivotal trials). Patient has multiple serious comorbidities that may further constrain tolerance for cytotoxic regimens.

Trial enrollment is one option but not the only one. Recommend the family discuss with the treating oncologist:
- Approved L4 SoC options: sotorasib + panitumumab (FDA approved for KRAS G12C mCRC), regorafenib, TAS-102 + bevacizumab, fruquintinib
- Best supportive care + palliative care consultation (orthogonal to anti-cancer treatment, not an alternative)
- Trial-specific logistics: travel, screening visits, and early-phase dosing uncertainty

Patient and family should hear realistic prognosis before committing to trial logistics. The decision is theirs.
```

## When NOT to trigger

Do NOT trigger GoC for:

- Patients on first line (regardless of comorbidities — first-line treatment options are usually robust)
- Patients with stable disease on current line and good performance status
- Patients with adjuvant intent (treatment is curative, not palliative)

## Output

```json
{
  "goals_of_care": {
    "triggered": true,
    "reasons": [
      "Line + cancer-type median OS: effective L3 ongoing → L4 next, CRC L3+ median OS ~6 months",
      "Cumulative comorbidity burden: three or more serious organ-system conditions"
    ],
    "discussion_recommendation": "string"
  }
}
```
