# decision-synthesizer output schema

The decision report is consumed by the report renderer. Examples must use synthetic patient and trial identifiers.

```json
{
      "report_version": "v2.0.0",
      "generated_at": "ISO-8601",
      "patient_summary": {
        "patient_id": "SYNTHETIC-PATIENT",
        "summary_text": "Structured synthetic patient summary",
        "cancer_type": "string",
        "stage": "string",
        "mutations": [],
        "biomarkers": {},
        "treatment_lines_completed": 0,
        "current_therapy_ongoing": false,
        "key_comorbidities": [],
        "ecog": 0,
        "country": "string",
        "patient_location": "synthetic location"
      },
      "consistency_flags": [],
      "goals_of_care": {
        "triggered": false,
        "reasons": [],
        "discussion_recommendation": ""
      },
      "decision_paths": [
        {
          "rank": 1,
          "role": "primary",
          "trial_id": "SYNTHETIC-TRIAL",
          "trial_title": "Synthetic trial title",
          "patient_country_site_count": 0,
          "feasibility_score": 0.0,
          "rationale": "Patient-specific rationale",
          "efficacy_snapshot": {},
          "vs_soc": {},
          "risks": [],
          "blockers_satisfied": [],
          "blockers_pending": [],
          "alternatives_comparison": [],
          "consequences_of_skipping": "",
          "estimated_timeline": {
            "screening_window": "",
            "earliest_first_dose": "",
            "critical_path_steps": []
          }
        }
      ],
      "soc_benchmarks": [],
      "match_inventory_size": {
        "match": 0,
        "conditional": 0,
        "exclude": 0
      },
      "v2_summary": {
        "total_trials_analyzed": 0,
        "decision_paths_emitted": 0
      }
}
```

## Field requirements

- report_version is required.
- patient_summary.summary_text is required.
- decision_paths must contain only non-excluded trials.
- decision_paths feasibility and patient-country site counts must be numeric.
- goals_of_care.discussion_recommendation is required when triggered is true.
- consistency_flags and redundancy notes must be arrays.
- approved off-trial alternatives must be disclosed when a path overlaps standard care.
