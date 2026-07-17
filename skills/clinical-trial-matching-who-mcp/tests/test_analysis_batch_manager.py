from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
from analysis_batch_manager import combine_analysis_stages, merge, status
from analysis_contract import (
    SCHEMA_VERSION,
    build_analysis_jobs,
    build_deep_analysis_jobs,
    validate_analysis_bundle,
)


def gating_item(trial_id: str, verdict: str) -> dict:
    return {
        "trial_id": trial_id,
        "gating": {
            "verdict": verdict,
            "confidence": 0.9,
            "inclusion_evaluation": [],
            "exclusion_evaluation": [],
            "hard_rules_triggered": [],
            "blockers_satisfied": [],
            "blockers_failed": [],
            "blockers_pending": [],
            "rationale": f"Model verdict: {verdict}",
        },
    }


def deep_item(trial_id: str) -> dict:
    return {
        "trial_id": trial_id,
        "risk_annotation": {"patient_cancer_context": "NSCLC", "risks": []},
        "efficacy_context": {
            "efficacy_snapshot": {
                "match_type": "no_data",
                "applies_because": "No applicable outcome data found.",
            },
            "development_evidence": [],
            "evidence_search": {
                "status": "no_relevant_publication",
                "searched_at": "2026-07-16",
                "queries": ["agent NSCLC"],
            },
            "vs_soc": {"available": False},
        },
    }


class AnalysisBatchManagerTests(unittest.TestCase):
    def test_status_reports_missing_and_duplicate_safe_coverage(self):
        jobs = {
            "batches": [
                {"trials": [{"id": "T1"}, {"id": "T2"}]},
                {"trials": [{"id": "T3"}]},
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jobs_path = root / "jobs.json"
            batch_dir = root / "batches"
            batch_dir.mkdir()
            jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
            (batch_dir / "batch-001.json").write_text(json.dumps({
                "analyzed_trials": [{"trial_id": "T1"}, {"trial_id": "T2"}]
            }), encoding="utf-8")
            result = status(jobs_path, batch_dir)
        self.assertEqual(result["expected"], 3)
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["missing"], ["T3"])
        self.assertFalse(result["complete"])

    def test_gater_jobs_cover_every_non_hard_excluded_trial_and_only_run_gater(self):
        jobs = build_analysis_jobs(
            {"cancer_type": "NSCLC"},
            [{"id": "T1"}, {"id": "T2"}, {"id": "HARD", "exclude_reason": "inactive"}],
            ROOT.parent,
            batch_size=1,
        )
        self.assertEqual(jobs["trial_count"], 2)
        self.assertEqual(jobs["hard_excluded_trial_ids"], ["HARD"])
        self.assertEqual(
            [trial["id"] for batch in jobs["batches"] for trial in batch["trials"]],
            ["T1", "T2"],
        )
        self.assertTrue(all(
            batch["required_execution_order"] == ["trial-gater"] for batch in jobs["batches"]
        ))

    def test_deep_jobs_are_created_only_for_match_and_conditional(self):
        jobs = build_deep_analysis_jobs(
            {"cancer_type": "NSCLC"},
            [{"id": "MATCH"}, {"id": "COND"}, {"id": "EXCLUDE"}],
            [gating_item("MATCH", "match"), gating_item("COND", "conditional"), gating_item("EXCLUDE", "exclude")],
            ROOT.parent,
        )
        deep_ids = [
            row["id"] for batch in jobs["batches"] for row in batch["trials"]
        ]
        self.assertEqual(deep_ids, ["MATCH", "COND"])
        self.assertEqual(jobs["excluded_trial_ids"], ["EXCLUDE"])

    def test_staged_merge_keeps_gater_exclude_and_attaches_deep_outputs(self):
        gating = [gating_item("KEEP", "conditional"), gating_item("DROP", "exclude")]
        combined = combine_analysis_stages(gating, [deep_item("KEEP")])
        by_id = {item["trial_id"]: item for item in combined}
        self.assertNotIn("risk_annotation", by_id["DROP"])
        self.assertIn("risk_annotation", by_id["KEEP"])
        bundle = {
            "schema_version": SCHEMA_VERSION,
            "analysis_provenance": {
                "mode": "llm_subskills", "model": "test", "completed_at": "now",
                "output_language": "en",
            },
            "analyzed_trials": combined,
            "decision_report": {"decision_paths": [], "goals_of_care": {}},
        }
        validated = validate_analysis_bundle(bundle, {"cancer_type": "NSCLC"}, ["KEEP", "DROP"])
        self.assertEqual(set(validated), {"KEEP", "DROP"})

    def test_staged_merge_writes_existing_analysis_bundle(self):
        jobs = {"batches": [{"trials": [{"id": "KEEP"}, {"id": "DROP"}]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gater_dir = root / "gater"
            deep_dir = root / "deep"
            gater_dir.mkdir()
            deep_dir.mkdir()
            paths = {
                "jobs": root / "jobs.json",
                "patient": root / "patient.json",
                "decision": root / "decision.json",
                "out": root / "analysis_bundle.json",
            }
            paths["jobs"].write_text(json.dumps(jobs), encoding="utf-8")
            paths["patient"].write_text(json.dumps({"cancer_type": "NSCLC"}), encoding="utf-8")
            paths["decision"].write_text(json.dumps({
                "decision_report": {"decision_paths": [], "goals_of_care": {}}
            }), encoding="utf-8")
            (gater_dir / "gater-batch-001.json").write_text(json.dumps({
                "analyzed_trials": [gating_item("KEEP", "match"), gating_item("DROP", "exclude")]
            }), encoding="utf-8")
            (deep_dir / "deep-batch-001.json").write_text(json.dumps({
                "analyzed_trials": [deep_item("KEEP")]
            }), encoding="utf-8")
            result = merge(
                paths["jobs"], paths["patient"], gater_dir, paths["decision"], paths["out"],
                "test-model", "en", deep_dir,
            )
            bundle = json.loads(paths["out"].read_text(encoding="utf-8"))
        self.assertTrue(result["validated"])
        self.assertEqual(bundle["schema_version"], SCHEMA_VERSION)
        self.assertEqual({row["trial_id"] for row in bundle["analyzed_trials"]}, {"KEEP", "DROP"})
    def test_staged_status_requires_deep_only_for_non_excluded_trials(self):
        jobs = {
            "schema_version": "clinical-analysis-jobs-v2",
            "batches": [{"trials": [{"id": "KEEP"}, {"id": "DROP"}]}],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jobs_path = root / "jobs.json"
            jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
            (root / "gater-batch-001.json").write_text(json.dumps({
                "analyzed_trials": [gating_item("KEEP", "match"), gating_item("DROP", "exclude")]
            }), encoding="utf-8")
            (root / "deep-batch-001.json").write_text(json.dumps({
                "analyzed_trials": [deep_item("KEEP")]
            }), encoding="utf-8")
            result = status(jobs_path, root)
        self.assertTrue(result["complete"])
        self.assertEqual(result["stages"]["gater"]["expected"], 2)
        self.assertEqual(result["stages"]["deep"]["expected"], 1)


if __name__ == "__main__":
    unittest.main()
