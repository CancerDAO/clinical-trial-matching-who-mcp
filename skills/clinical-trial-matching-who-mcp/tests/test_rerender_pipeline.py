from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "render"))

from rerender_pipeline import refresh_presentational_fields


class RerenderPipelineTests(unittest.TestCase):
    def test_refreshes_presentation_without_promoting_validation_artifact(self):
        payload = {
            "formal_report_ready": False,
            "patient": {
                "patient_id": "SYNTHETIC-1",
                "country": "United States",
                "cancer_type": "NSCLC",
                "mutations": ["EGFR ex19del"],
            },
            "trials": [{
                "id": "NCT00000001",
                "scientific_title": "A Study of Osimertinib in NSCLC",
                "interventions": ["Osimertinib", "Computed Tomography"],
                "countries": ["United States"],
                "patient_country_location_record_count": 1,
                "gating": {"verdict": "conditional"},
            }],
        }
        refreshed = refresh_presentational_fields(payload)
        self.assertFalse(refreshed["formal_report_ready"])
        self.assertEqual(refreshed["counts"]["conditional"], 1)
        self.assertEqual(refreshed["geography_audit"]["country_unverified"], 1)
        self.assertNotIn("Computed Tomography", refreshed["trials"][0]["display_title"])
        self.assertTrue(refreshed["presentation_provenance"]["clinical_analysis_preserved"])


if __name__ == "__main__":
    unittest.main()
