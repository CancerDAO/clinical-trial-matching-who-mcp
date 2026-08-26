from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from clinical_fact_grounding import correct_analysis_clinical_facts


class ClinicalFactGroundingTests(unittest.TestCase):
    def test_rmc_6236_is_not_treated_as_immunotherapy(self):
        item = {
            "trial_id": "NCT1",
            "gating": {
                "verdict": "exclude", "confidence": 0.9,
                "blockers_satisfied": [],
                "blockers_failed": [
                    "Prior immunotherapy (RMC-6236 ongoing) — violates exclusion criterion"
                ],
                "blockers_pending": [], "hard_rules_triggered": ["R1"],
                "rationale": "RMC-6236 is an investigational immunotherapy.",
            },
        }
        corrected = correct_analysis_clinical_facts(item, allow_verdict_change=True)
        gating = corrected["gating"]
        self.assertEqual(gating["verdict"], "conditional")
        self.assertEqual(gating["blockers_failed"], [])
        self.assertNotIn("R1", gating["hard_rules_triggered"])
        self.assertIn("not immunotherapy", " ".join(gating["blockers_pending"]))
        self.assertIn("pan-RAS/RAS(ON) inhibitor", gating["rationale"])

    def test_uln_threshold_contradiction_is_moved_to_pending(self):
        item = {
            "trial_id": "NCT2",
            "gating": {
                "verdict": "conditional", "confidence": 0.8,
                "blockers_satisfied": ["Adequate organ function per screening labs"],
                "blockers_failed": [], "blockers_pending": [],
                "hard_rules_triggered": [], "rationale": "candidate",
                "inclusion_evaluation": [{
                    "criterion": "ALT/AST ≤1.5×ULN (≤5×ULN with liver metastases)",
                    "verdict": "✅ 符合",
                    "evidence": "ALT 5.9×ULN (within ≤5×ULN for hepatic mets)",
                }],
                "exclusion_evaluation": [],
            },
        }
        gating = correct_analysis_clinical_facts(item)["gating"]
        self.assertEqual(gating["blockers_satisfied"], [])
        self.assertIn("ALT 5.9×ULN exceeds", gating["blockers_pending"][0])
        self.assertEqual(
            gating["inclusion_evaluation"][0]["verdict"], "❌ 不符合"
        )


if __name__ == "__main__":
    unittest.main()
