from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in ("scripts/pipeline", "scripts/retrieval"):
    sys.path.insert(0, str(ROOT / relative))

from recall_triage import score_recall_anchor, stratify_recall_candidates


class RecallTriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient = {
            "cancer_type": "colorectal cancer",
            "mutations": ["KRAS G12C"],
            "country": "China",
        }

    def test_exact_disease_and_molecular_trial_is_primary(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT1",
            "title": "KRAS G12C inhibitor in colorectal cancer",
            "overall_status": "RECRUITING",
            "live_registry_verification": {"status": "active"},
        })
        self.assertEqual(audit["tier"], "gater_primary")
        self.assertIn("direct_disease_anchor", audit["reasons"])
        self.assertIn("exact_molecular_anchor", audit["reasons"])

    def test_molecular_basket_trial_is_secondary_not_dropped(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT2",
            "disease_text": "Advanced solid tumors with KRAS G12C mutation",
            "live_registry_verification": {"status": "active"},
        })
        self.assertEqual(audit["tier"], "gater_secondary")

    def test_unknown_status_with_only_generic_anchor_is_deferred(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT3",
            "disease_text": "Advanced solid tumor",
            "matched_by": ["generic oncology"],
            "live_registry_verification": {"status": "unknown"},
        })
        self.assertEqual(audit["tier"], "deferred_audit")
        self.assertIn("unknown_registry_status_with_weak_anchor", audit["reasons"])

    def test_unknown_status_does_not_defer_strong_anchor(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT4",
            "title": "KRAS G12C colorectal cancer cohort",
            "live_registry_verification": {"status": "unknown"},
        })
        self.assertEqual(audit["tier"], "gater_primary")

    def test_retrieval_query_is_not_clinical_evidence(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT-query-only",
            "title": "A general oncology platform study",
            "matched_queries": ["colorectal cancer KRAS G12C"],
            "matched_by": ["disease_biomarker", "pathway_resistance"],
            "patient_country_site_count": 5,
            "live_registry_verification": {"status": "active"},
        })
        self.assertEqual(audit["tier"], "deferred_audit")
        self.assertNotIn("direct_disease_anchor", audit["reasons"])

    def test_negative_disease_context_does_not_promote_trial(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT-negative",
            "eligibility_full": "Patients with colorectal cancer are excluded.",
            "matched_queries": ["colorectal cancer precision oncology"],
            "live_registry_verification": {"status": "active"},
        })
        self.assertEqual(audit["tier"], "deferred_audit")
        self.assertIn("negative_disease_context", audit["reasons"])

    def test_country_and_multiple_queries_do_not_create_primary_evidence(self) -> None:
        audit = score_recall_anchor(self.patient, {
            "id": "NCT-disease-only",
            "disease_text": "Metastatic colorectal cancer",
            "matched_by": ["disease", "immune"],
            "patient_country_site_count": 8,
            "live_registry_verification": {"status": "active"},
        })
        self.assertEqual(audit["tier"], "gater_secondary")

    def test_stratification_disposes_every_id_once(self) -> None:
        result = stratify_recall_candidates(self.patient, [
            {"id": "A", "title": "KRAS G12C colorectal cancer"},
            {"id": "B", "title": "KRAS G12C solid tumor"},
            {"id": "C", "title": "General oncology supportive care"},
        ])
        ids = [
            trial["id"]
            for tier in ("gater_primary", "gater_secondary", "deferred_audit")
            for trial in result[tier]
        ]
        self.assertEqual(sorted(ids), ["A", "B", "C"])
        self.assertTrue(result["audit"]["disposition_complete"])


if __name__ == "__main__":
    unittest.main()
