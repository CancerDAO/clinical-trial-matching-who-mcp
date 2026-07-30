from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from evidence_grounding import ground_development_evidence
from decision_grounding import ground_decision_report


class EvidenceGroundingTests(unittest.TestCase):
    def test_prefetch_supplies_citation_for_compact_model_evidence(self):
        efficacy = {
            "development_evidence": [{
                "url": "https://europepmc.org/article/MED/12345",
                "findings": "Relevant result",
                "applicability": "Same biomarker",
                "limitations": "Early phase",
                "evidence_stage": "phase_1",
            }]
        }
        ground_development_evidence(efficacy, {
            "status": "found",
            "searched_at": "2026-07-29T00:00:00Z",
            "queries": ["NCT1"],
            "candidates": [{
                "title": "Grounded study",
                "authors": "A Author",
                "year": "2026",
                "pmid": "12345",
                "url": "https://europepmc.org/article/MED/12345",
            }],
        })
        evidence = efficacy["development_evidence"][0]
        self.assertIn("Grounded study", evidence["citation"])
        self.assertEqual(evidence["source_identifiers"]["pmid"], "12345")

    def test_only_prefetched_publications_survive(self):
        efficacy = {
            "development_evidence": [
                {
                    "citation": "Model citation PMID 12345",
                    "url": "https://europepmc.org/article/MED/12345",
                    "findings": "Relevant result",
                    "applicability": "Same biomarker",
                    "limitations": "Early phase",
                    "evidence_stage": "phase_1",
                },
                {
                    "citation": "Invented PMID 99999",
                    "url": "https://europepmc.org/article/MED/99999",
                    "findings": "Invented",
                    "applicability": "Unknown",
                    "limitations": "Unknown",
                    "evidence_stage": "phase_1",
                },
            ]
        }
        prefetch = {
            "status": "found", "searched_at": "2026-07-29T00:00:00Z",
            "queries": ["NCT00000000"], "source": "Europe PMC REST API",
            "candidates": [{
                "title": "Grounded study", "authors": "A Author",
                "journal": "Journal", "year": "2026", "pmid": "12345",
                "url": "https://europepmc.org/article/MED/12345",
                "source": "Europe PMC",
            }],
        }
        audit = ground_development_evidence(efficacy, prefetch)
        self.assertEqual(len(efficacy["development_evidence"]), 1)
        self.assertIn("Grounded study", efficacy["development_evidence"][0]["citation"])
        self.assertEqual(efficacy["evidence_search"]["rejected_model_evidence_count"], 1)
        self.assertEqual(audit["grounded_count"], 1)

    def test_decision_clinical_fields_are_restored_from_validated_input(self):
        decision = {
            "decision_paths": [{
                "trial_id": "NCT1",
                "efficacy_snapshot": {"metrics": {"orr": 0.99}},
                "risks": [{"key": "invented"}],
                "estimated_timeline": {
                    "screening_window": "tomorrow",
                    "earliest_first_dose": "next week",
                    "critical_path_steps": ["Contact site"],
                },
            }]
        }
        source = [{
            "trial_id": "NCT1", "title": "Source title", "sponsor": "Sponsor",
            "phase": ["PHASE1"], "feasibility_score": 0.3,
            "gating": {
                "verdict": "conditional", "blockers_satisfied": [],
                "blockers_failed": [], "blockers_pending": ["CBC"],
            },
            "risk_summary": {"risks": [{"key": "grounded"}]},
            "efficacy_summary": {
                "match_type": "no_data", "metrics": {}, "evidence_source": None,
                "applies_because": "No applicable results",
                "vs_soc": {"available": False},
            },
        }]
        grounded = ground_decision_report(decision, source)["decision_paths"][0]
        self.assertTrue(grounded["requires_eligibility_confirmation"])
        self.assertEqual(grounded["risks"], [{"key": "grounded"}])
        self.assertIsNone(grounded["estimated_timeline"]["earliest_first_dose"])
        self.assertNotIn("0.99", grounded["consequences_of_skipping"])
        self.assertIn(
            "cannot establish superiority",
            grounded["vs_soc"]["comparison_limitation"],
        )
