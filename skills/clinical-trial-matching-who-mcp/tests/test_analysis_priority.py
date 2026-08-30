from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "scripts/pipeline", "scripts/render", "scripts/retrieval", "scripts/classification",
):
    sys.path.insert(0, str(ROOT / relative))

from analysis_contract import (
    build_analysis_jobs, build_deep_analysis_jobs, compact_trial_for_analysis,
    normalized_report_analysis, validate_analysis_bundle,
)
from analysis_batch_manager import combine_analysis_stages
from analysis_priority import (
    assign_analysis_priority, coverage_mode, gater_trials_for_coverage,
    promote_fallback_priority,
)
from html_renderer import render_patient_html
from mcp_transport import execute_who_workflow


def _trial(**overrides):
    trial = {
        "id": "NCT-A",
        "title": "KRAS G12C CRC study",
        "disease_text": "colorectal cancer KRAS G12C",
        "overall_status": "RECRUITING",
        "matched_by": ["disease_biomarker"],
        "matched_queries": [{"condition": "colorectal cancer", "term": "KRAS G12C"}],
        "patient_country_site_count": 2,
        "country_assessment": {"class": "domestic_named"},
        "recall_triage": {
            "tier": "gater_primary", "score": 9, "reasons": ["direct_disease_anchor"],
        },
        "feasibility": {"composite": 0.8},
    }
    trial.update(overrides)
    return trial


def _patient():
    return {
        "patient_id": "PT-1", "country": "China", "cancer_type": "colorectal cancer",
        "mutations": ["KRAS G12C"], "stage": "IV",
    }


def gating_item(trial_id: str, verdict: str) -> dict:
    return {
        "trial_id": trial_id,
        "gating": {
            "verdict": verdict, "confidence": 0.9,
            "inclusion_evaluation": [], "exclusion_evaluation": [],
            "hard_rules_triggered": [], "blockers_satisfied": [],
            "blockers_failed": [], "blockers_pending": [],
            "rationale": f"Model verdict: {verdict}",
        },
    }


class AnalysisPriorityTests(unittest.TestCase):
    def test_in_country_recruiting_primary_is_band_a(self):
        tagged = assign_analysis_priority(_patient(), _trial())
        self.assertEqual(tagged["band"], "A")
        self.assertTrue(tagged["deep_required"])
        self.assertEqual(tagged["gater_mode"], "full")

    def test_overseas_secondary_is_band_b(self):
        tagged = assign_analysis_priority(_patient(), _trial(
            id="NCT-B",
            patient_country_site_count=0,
            country_assessment={"class": "overseas"},
            overall_status="UNKNOWN",
            recall_triage={"tier": "gater_secondary", "score": 3, "reasons": []},
        ))
        self.assertEqual(tagged["band"], "B")
        self.assertFalse(tagged["deep_required"])
        self.assertEqual(tagged["gater_mode"], "compact")

    def test_inactive_or_deferred_is_band_c(self):
        tagged = assign_analysis_priority(_patient(), _trial(
            overall_status="COMPLETED",
            recall_triage={"tier": "deferred_audit", "score": 1, "reasons": []},
        ))
        self.assertEqual(tagged["band"], "C")
        self.assertFalse(tagged["gater_required"])

    def test_empty_band_a_promotes_strongest_b(self):
        trials = [
            _trial(
                id="NCT-B1",
                analysis_priority={"band": "B", "in_country": True, "recruitment_status": "active"},
                recall_triage={"score": 5},
            ),
            _trial(
                id="NCT-B2",
                analysis_priority={"band": "B", "in_country": False, "recruitment_status": "unknown"},
                recall_triage={"score": 4},
            ),
        ]
        promote_fallback_priority(trials, limit=1)
        self.assertEqual(trials[0]["analysis_priority"]["band"], "A")
        self.assertTrue(trials[0]["analysis_priority"]["promoted"])
        self.assertEqual(trials[1]["analysis_priority"]["band"], "B")

    def test_patient_coverage_gates_only_band_a(self):
        trials = [
            _trial(id="A", analysis_priority={"band": "A", "gater_required": True}),
            _trial(id="B", analysis_priority={"band": "B", "gater_required": True}),
        ]
        selected = gater_trials_for_coverage(trials, "patient")
        self.assertEqual([trial["id"] for trial in selected], ["A"])
        self.assertEqual(
            [trial["id"] for trial in gater_trials_for_coverage(trials, "full")],
            ["A", "B"],
        )

    def test_coverage_mode_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "patient or full"):
            coverage_mode("audit")

    def test_gater_jobs_drop_full_eligibility_text(self):
        compact = compact_trial_for_analysis({
            "id": "T1", "title": "Targeted trial",
            "eligibility_full": "very long eligibility text",
            "eligibility_excerpt": "excerpt",
            "parsed_criteria": {"inclusion": ["advanced cancer"]},
            "patient_country_sites": [{"site_name": "A", "country": "China"}],
        })
        self.assertNotIn("eligibility_full", compact)
        self.assertNotIn("eligibility_excerpt", compact)
        self.assertIn("parsed_criteria", compact)
        jobs = build_analysis_jobs(
            {"cancer_type": "NSCLC"},
            [{
                "id": "T1", "eligibility_full": "very long",
                "analysis_priority": {"band": "A", "gater_mode": "full", "deep_required": True},
            }],
            ROOT.parent,
            batch_size=1,
        )
        self.assertNotIn("eligibility_full", jobs["batches"][0]["trials"][0])
        self.assertEqual(jobs["deep_required_trial_ids"], ["T1"])

    def test_band_b_uses_compact_gater_and_skips_deep(self):
        trials = [
            {
                "id": "A", "title": "Primary",
                "parsed_criteria": {"inclusion": ["x"]},
                "eligibility_full": "long A",
                "analysis_priority": {
                    "band": "A", "gater_mode": "full", "deep_required": True,
                    "gater_required": True,
                },
            },
            {
                "id": "B", "title": "Basket",
                "parsed_criteria": {"inclusion": ["y"]},
                "eligibility_full": "long B",
                "analysis_priority": {
                    "band": "B", "gater_mode": "compact", "deep_required": False,
                    "gater_required": True,
                },
            },
        ]
        jobs = build_analysis_jobs({"cancer_type": "NSCLC"}, trials, ROOT.parent, batch_size=8)
        by_id = {row["id"]: row for batch in jobs["batches"] for row in batch["trials"]}
        self.assertIn("parsed_criteria", by_id["A"])
        self.assertNotIn("parsed_criteria", by_id["B"])
        self.assertEqual(jobs["deep_required_trial_ids"], ["A"])
        deep = build_deep_analysis_jobs(
            {"cancer_type": "NSCLC"}, trials,
            [gating_item("A", "conditional"), gating_item("B", "match")],
            ROOT.parent, deep_required_ids=jobs["deep_required_trial_ids"],
        )
        self.assertEqual(
            [row["id"] for batch in deep["batches"] for row in batch["trials"]],
            ["A"],
        )
        combined = combine_analysis_stages(
            [gating_item("A", "conditional"), gating_item("B", "match")],
            [{
                "trial_id": "A",
                "risk_annotation": {"patient_cancer_context": "NSCLC", "risks": []},
                "efficacy_context": {
                    "efficacy_snapshot": {"match_type": "no_data", "applies_because": "none"},
                    "development_evidence": [],
                    "evidence_search": {
                        "status": "no_relevant_publication",
                        "searched_at": "2026-07-16", "queries": ["q"],
                    },
                    "vs_soc": {"available": False},
                },
            }],
            jobs["deep_required_trial_ids"],
        )
        bundle = {
            "schema_version": "clinical-subskills-analysis-v1",
            "analysis_provenance": {
                "mode": "llm_subskills", "model": "test", "completed_at": "now",
                "output_language": "en",
            },
            "analyzed_trials": combined,
            "decision_report": {"decision_paths": [], "goals_of_care": {}},
        }
        validated = validate_analysis_bundle(
            bundle, {"cancer_type": "NSCLC"}, ["A", "B"],
            deep_required_ids=jobs["deep_required_trial_ids"],
        )
        self.assertEqual(set(validated), {"A", "B"})
        self.assertNotIn("risk_annotation", validated["B"])
        normalized = normalized_report_analysis({
            **validated["B"],
            "analysis_priority": trials[1]["analysis_priority"],
        })
        self.assertIn("Compact gater only", normalized["efficacy_context"]["summary"])

    def test_untagged_match_still_requires_deep(self):
        item = gating_item("KEEP", "conditional")
        with self.assertRaisesRegex(Exception, "risk"):
            validate_analysis_bundle(
                {
                    "schema_version": "clinical-subskills-analysis-v1",
                    "analysis_provenance": {
                        "mode": "llm_subskills", "model": "test",
                        "completed_at": "now", "output_language": "en",
                    },
                    "analyzed_trials": [item],
                    "decision_report": {"decision_paths": [], "goals_of_care": {}},
                },
                {"cancer_type": "NSCLC"},
                ["KEEP"],
            )

    def test_patient_html_omits_audit_hashes_and_exclude_cards(self):
        payload = {
            "language": "zh-CN",
            "patient": {"patient_id": "P1", "country": "China", "cancer_type": "CRC", "stage": "IV", "mutations": ["KRAS G12C"]},
            "database_as_of": "2026-07-16",
            "decision_report": {
                "patient_summary": {"summary_text": "先核实国内可及试验。"},
                "decision_paths": [{
                    "rank": 1, "trial_id": "NCT-A", "trial_title": "Adagrasib",
                    "rationale": "国内可及，值得优先核实。",
                    "blockers_pending": ["最近化验"],
                }],
                "goals_of_care": {},
            },
            "trials": [
                {
                    "id": "NCT-A", "display_title": "Adagrasib", "phases": ["PHASE2"],
                    "overall_status": "RECRUITING",
                    "resolved_source_url": "https://clinicaltrials.gov/study/NCT-A",
                    "country_assessment": {"class": "domestic_named"},
                    "patient_country_site_count": 3,
                    "gating": {"verdict": "conditional", "rationale": "需确认实验室", "pending": ["lab"]},
                    "analysis_priority": {"band": "A"},
                },
                {
                    "id": "NCT-X", "display_title": "Excluded", "phases": [],
                    "overall_status": "RECRUITING",
                    "resolved_source_url": "https://clinicaltrials.gov/study/NCT-X",
                    "country_assessment": {"class": "overseas"},
                    "gating": {"verdict": "exclude", "rationale": "癌种不符", "pending": []},
                },
            ],
            "run_manifest": {"prepared_sha256": "abc", "analysis_sha256": "def"},
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.html"
            render_patient_html(payload, path)
            html = path.read_text(encoding="utf-8")
        self.assertIn("您可以优先核实的临床试验", html)
        self.assertIn("国内可及，值得优先核实。", html)
        self.assertIn("最近化验", html)
        self.assertNotIn("SHA-256", html)
        self.assertNotIn("Excluded", html)
        self.assertNotIn("abc", html)

    def test_unique_get_trial_and_optional_skip(self):
        calls = []

        class FakeClient:
            protocol_version = "2024-11-05"

            def request(self, method, params=None):
                if method == "initialize":
                    return {"protocolVersion": "2024-11-05", "serverInfo": {"name": "fake"}}
                if method == "tools/list":
                    return {"tools": [{"name": name} for name in (
                        "database_metadata", "execute_search_plan", "get_trial"
                    )]}
                raise AssertionError(method)

            def notify(self, method, params=None):
                return None

            def call_tool(self, name, arguments):
                calls.append((name, arguments))
                if name == "database_metadata":
                    return {"database_as_of": "2026-07-16T00:00:00+00:00"}
                if name == "execute_search_plan":
                    return {
                        "results": [
                            {"id": "NCT1", "primary_registry_id": "NCT1"},
                            {"id": "NCT1", "primary_registry_id": "NCT1"},
                            {"id": "NCT2", "primary_registry_id": "NCT2"},
                        ],
                        "search_stats": {},
                    }
                if name == "get_trial":
                    return {"id": arguments["registry_id"], "found": True}
                raise AssertionError(name)

        result = execute_who_workflow(
            FakeClient(), transport_name="fake", client_version="test",
            search_plan={"keyword_groups": []}, max_per_query=5, total_limit=5,
        )
        self.assertEqual(result["registry_ids"], ["NCT1", "NCT2"])
        self.assertEqual(
            [arguments["registry_id"] for name, arguments in calls if name == "get_trial"],
            ["NCT1", "NCT2"],
        )
        calls.clear()
        with mock.patch.dict(os.environ, {"MCP_FETCH_DETAILS": "0"}):
            skipped = execute_who_workflow(
                FakeClient(), transport_name="fake", client_version="test",
                search_plan={"keyword_groups": []}, max_per_query=5, total_limit=5,
            )
        self.assertEqual(skipped["details"], [])
        self.assertFalse(any(name == "get_trial" for name, _ in calls))


if __name__ == "__main__":
    unittest.main()
