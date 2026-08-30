from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))

from country_scope import (  # noqa: E402
    canonicalize_country, filter_trials_for_country, resolve_recall_country,
)


class CountryScopeTests(unittest.TestCase):
    def test_chinese_country_alias_maps_to_mcp_country(self):
        self.assertEqual(canonicalize_country("中国大陆"), "China")
        self.assertEqual(canonicalize_country("PR China"), "China")

    def test_global_scope_preserves_existing_behavior(self):
        with patch.dict(os.environ, {"TRIAL_RECALL_SCOPE": "global"}, clear=False):
            result = resolve_recall_country({"country": "中国"})
        self.assertEqual(result["mcp_country"], "")
        self.assertEqual(result["mapping_source"], "global_scope")

    def test_patient_country_wins_over_model_plan_candidate(self):
        with patch.dict(os.environ, {
            "TRIAL_RECALL_SCOPE": "patient_country",
            "TRIAL_RECALL_DEFAULT_COUNTRY": "China",
        }, clear=False):
            result = resolve_recall_country(
                {"country": "美国"}, plan_country="China"
            )
        self.assertEqual(result["mcp_country"], "United States")
        self.assertEqual(result["mapping_source"], "patient_country")

    def test_missing_country_uses_configured_china_default(self):
        with patch.dict(os.environ, {
            "TRIAL_RECALL_SCOPE": "patient_country",
            "TRIAL_RECALL_DEFAULT_COUNTRY": "China",
        }, clear=False):
            result = resolve_recall_country({}, plan_country="")
        self.assertEqual(result["mcp_country"], "China")
        self.assertTrue(result["default_country_used"])

    def test_portal_country_filter_uses_structured_evidence(self):
        retained, audit = filter_trials_for_country([
            {"id": "CN", "country_records": [{"country": "中国"}]},
            {"id": "US", "sites": [{"country": "United States"}]},
        ], "China")
        self.assertEqual([trial["id"] for trial in retained], ["CN"])
        self.assertEqual(audit["removed_count"], 1)


if __name__ == "__main__":
    unittest.main()
