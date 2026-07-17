from __future__ import annotations

import random
import string
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in ("scripts/retrieval", "scripts/scoring", "scripts/classification"):
    sys.path.insert(0, str(ROOT / relative))

from feasibility import compute_feasibility
from mechanism_categories import CATEGORY_ORDER, classify_mechanism
from who_mcp_adapter import merge_sources, normalize_trial


class DeterministicPropertyTests(unittest.TestCase):
    def test_feasibility_scores_remain_bounded_across_random_inputs(self):
        rng = random.Random(20260714)
        countries = ["China", "United States", "Germany", "", "中国"]
        statuses = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED", ""]
        for _ in range(250):
            country = rng.choice(countries)
            sites = [{"country": rng.choice(countries), "city": "City"} for _ in range(rng.randrange(0, 15))]
            trial = {
                "overall_status": rng.choice(statuses), "last_update_date": rng.choice(["2026-07-01", "2024-01-01", "", "bad-date"]),
                "sites": sites, "interventions": rng.choice([[], ["CAR-T"], ["Drug A"]]),
            }
            patient = {
                "country": country, "city": "City", "affordability_tier": rng.choice(["low", "medium", "high", "unknown"]),
                "willing_to_travel_internationally": rng.choice([True, False]), "treatment_lines_completed": rng.randrange(0, 6),
            }
            result = compute_feasibility(trial, patient)
            self.assertGreaterEqual(result.composite, 0)
            self.assertLessEqual(result.composite, 1)
            self.assertTrue(all(0 <= value <= 1 for value in result.sub_scores.values()))

    def test_sparse_delta_never_blanks_nonempty_local_search_fields(self):
        rng = random.Random(17)
        for index in range(100):
            trial_id = f"NCT{index:08d}"
            local = [{
                "primary_registry_id": trial_id, "trial_uid": f"uid-{index}", "title": f"Title {index}",
                "brief_summary": "summary", "phase_normalized": "Phase 2", "intervention_summary": "Drug X",
                "last_update_date": "2026-07-01",
            }]
            delta = [{"id": trial_id, "title": rng.choice(["", None]), "brief_summary": "", "last_update_date": "2026-07-10"}]
            result = merge_sources(local, delta, patient={"country": "Germany"}, database_as_of="2026-07-09")[0]
            self.assertEqual(result["title"], f"Title {index}")
            self.assertEqual(result["brief_summary"], "summary")
            self.assertEqual(result["interventions"], ["Drug X"])

    def test_normalization_and_classification_accept_unicode_and_long_text(self):
        rng = random.Random(99)
        for index in range(100):
            suffix = "".join(rng.choice(string.ascii_letters) for _ in range(200))
            source = {
                "id": f"ChiCTR{index}", "title": f"实体瘤 CAR-T {suffix}", "countries": "中国|United States",
                "intervention_summary": "CAR-T|PD-1", "phase": "Phase 1;Phase 2",
            }
            trial = normalize_trial(source, patient_country="中国", provenance="test")
            category = classify_mechanism(trial)["category"]
            self.assertIn(category, CATEGORY_ORDER)
            self.assertEqual(trial["phases"], ["PHASE_1", "PHASE_2"])
            self.assertEqual(trial["interventions"], ["CAR-T", "PD-1"])


if __name__ == "__main__":
    unittest.main()
