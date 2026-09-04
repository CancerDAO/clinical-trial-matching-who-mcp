from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from analysis_priority import (
    annotate_analysis_priority,
    coverage_mode,
    patient_priority_rows,
    promote_empty_band_a,
)


class AnalysisPriorityTests(unittest.TestCase):
    def test_primary_in_country_is_patient_priority(self) -> None:
        rows = annotate_analysis_priority([{
            "id": "NCT-A",
            "overall_status": "RECRUITING",
            "patient_country_site_count": 2,
            "recall_triage": {"tier": "gater_primary", "score": 8},
        }])
        self.assertEqual(rows[0]["analysis_priority"]["band"], "A")
        self.assertEqual([row["id"] for row in patient_priority_rows(rows)], ["NCT-A"])

    def test_secondary_and_weak_rows_remain_auditable(self) -> None:
        rows = annotate_analysis_priority([
            {
                "id": "NCT-B", "overall_status": "RECRUITING",
                "recall_triage": {"tier": "gater_secondary", "score": 4},
            },
            {
                "id": "NCT-C", "overall_status": "UNKNOWN",
                "recall_triage": {"tier": "deferred_audit", "score": 0},
            },
        ])
        self.assertEqual([row["analysis_priority"]["band"] for row in rows], ["B", "C"])

    def test_empty_band_a_promotes_a_bounded_fallback(self) -> None:
        rows = annotate_analysis_priority([
            {
                "id": f"NCT-{index}", "overall_status": "RECRUITING",
                "recall_triage": {"tier": "gater_secondary", "score": index},
            }
            for index in range(5)
        ])
        with mock.patch.dict(os.environ, {"PATIENT_PRIORITY_FALLBACK_LIMIT": "2"}):
            promoted = promote_empty_band_a(rows)
        selected = patient_priority_rows(promoted)
        self.assertEqual(len(selected), 2)
        self.assertEqual({row["id"] for row in selected}, {"NCT-3", "NCT-4"})
        self.assertTrue(all(row["analysis_priority"]["promoted"] for row in selected))

    def test_full_and_patient_are_the_only_modes(self) -> None:
        self.assertEqual(coverage_mode("patient"), "patient")
        self.assertEqual(coverage_mode("full"), "full")
        with self.assertRaises(ValueError):
            coverage_mode("balanced")


if __name__ == "__main__":
    unittest.main()
