from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
from generic_hard_rules import apply_generic_hard_rules, evaluate_generic_hard_rules


class GenericHardRuleTests(unittest.TestCase):
    def test_clear_structured_conflicts_are_all_audited(self):
        patient = {"age_years": 17, "sex_at_birth": "female", "ecog": 3,
                   "treatment_lines_completed": 4, "pregnant": True}
        trial = {"structured_eligibility": {"minimum_age": "18 Years", "sex": "Male", "ecog_max": 1,
                                             "maximum_prior_lines": 2, "allows_pregnancy": False}}
        result = evaluate_generic_hard_rules(patient, trial)
        self.assertEqual(result["disposition"], "hard_exclude")
        self.assertTrue(result["hard_exclude"])
        self.assertFalse(result["pass_to_gater"])
        self.assertEqual({item["rule_id"] for item in result["triggered_rules"]}, {
            "GHR-AGE-MIN", "GHR-SEX", "GHR-ECOG-MAX", "GHR-PRIOR-LINES-MAX", "GHR-PREGNANCY"})
        self.assertTrue(all("patient_value" in item and "trial_value" in item for item in result["triggered_rules"]))

    def test_boundaries_are_inclusive_and_pass_to_gater(self):
        patient = {"age": 18, "sex": "F", "ecog_performance_status": 1, "treatment_lines": 2}
        trial = {"eligibility": {"minimum_age": "216 Months", "maximum_age": "18 Years", "gender": "ALL",
                                  "minimum_ecog": 1, "maximum_ecog": 1,
                                  "minimum_prior_lines": 2, "maximum_prior_lines": 2}}
        result = evaluate_generic_hard_rules(patient, trial)
        self.assertEqual(result["disposition"], "pass_to_gater")
        self.assertFalse(result["hard_exclude"])
        self.assertTrue(result["pass_to_gater"])
        self.assertEqual(result["triggered_rules"], [])

    def test_missing_ambiguous_and_free_text_facts_never_hard_exclude(self):
        patient = {"age": "adult", "sex": "unknown", "ecog": "0-1"}
        trial = {"title": "Women age 18+ with ECOG 0 only",
                 "parsed_criteria": {"inclusion": ["Male participants are excluded", "No prior therapy"]},
                 "eligibility_full": "Age >= 18; ECOG 0; female only"}
        result = evaluate_generic_hard_rules(patient, trial)
        self.assertEqual(result["disposition"], "pass_to_gater")
        self.assertEqual(result["triggered_rules"], [])

    def test_age_above_maximum_uses_top_level_registry_fields(self):
        result = evaluate_generic_hard_rules(
            {"age_years": 66}, {"id": "T1", "minimum_age": "18 Years", "maximum_age": "65 Years"})
        self.assertEqual([rule["rule_id"] for rule in result["triggered_rules"]], ["GHR-AGE-MAX"])

    def test_unknown_pregnancy_permission_passes_to_gater(self):
        patient = {"pregnant": True}
        self.assertTrue(evaluate_generic_hard_rules(patient, {})["pass_to_gater"])
        self.assertTrue(evaluate_generic_hard_rules(
            patient, {"eligibility": {"allows_pregnancy": "unknown"}})["pass_to_gater"])

    def test_structured_observational_record_is_excluded_from_treatment_matching(self):
        result = evaluate_generic_hard_rules(
            {"cancer_type": "colorectal cancer"},
            {"id": "OBS1", "study_type_normalized": "Observational"},
        )
        self.assertEqual(result["disposition"], "hard_exclude")
        self.assertEqual(
            [item["rule_id"] for item in result["triggered_rules"]],
            ["GHR-NONINTERVENTIONAL-STUDY"],
        )

    def test_free_text_observational_word_is_not_a_hard_exclusion(self):
        result = evaluate_generic_hard_rules(
            {}, {"title": "Observational signals in an interventional study"}
        )
        self.assertTrue(result["pass_to_gater"])

    def test_batch_partitions_trials_preserves_inputs_and_exposes_audit(self):
        trials = [{"id": "too-young", "minimum_age": "18 Years"},
                  {"id": "review", "parsed_criteria": {"inclusion": ["specialist review required"]}}]
        original = deepcopy(trials)
        result = apply_generic_hard_rules({"age_years": 16}, trials)
        self.assertEqual([item["id"] for item in result["hard_exclude"]], ["too-young"])
        self.assertEqual([item["id"] for item in result["pass_to_gater"]], ["review"])
        self.assertEqual([item["trial_id"] for item in result["audit"]], ["too-young", "review"])
        self.assertEqual(trials, original)
        self.assertIn("generic_hard_rules", result["hard_exclude"][0])

    def test_invalid_inputs_raise_type_error(self):
        with self.assertRaises(TypeError):
            evaluate_generic_hard_rules([], {})
        with self.assertRaises(TypeError):
            apply_generic_hard_rules({}, [{"id": "ok"}, "bad"])


if __name__ == "__main__":
    unittest.main()
