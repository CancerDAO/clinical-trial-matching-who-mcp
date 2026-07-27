from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
for relative in ("scripts/pipeline", "scripts/render"):
    sys.path.insert(0, str(ROOT / relative))

import run_formal_pipeline as formal
from html_renderer import render_validation_html


class FormalPipelineStateTests(unittest.TestCase):
    def test_execute_command_advances_all_stages_without_model_selected_subset(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            patient = run_dir / "patient.json"
            patient.write_text('{"country":"China"}', encoding="utf-8")
            base = {
                "patient_path": str(patient),
                "gater_jobs_path": str(run_dir / "analysis_jobs.json"),
                "gater_batch_dir": str(run_dir / "gater-batches"),
                "deep_jobs_path": str(run_dir / "deep_jobs.json"),
                "deep_batch_dir": str(run_dir / "deep-batches"),
            }
            states = [
                {**base, "stage": "gater_pending"},
                {**base, "stage": "deep_pending"},
                {**base, "stage": "analysis_merged"},
            ]
            with mock.patch.object(formal, "_load_state", side_effect=states), \
                 mock.patch.object(formal, "execute_batches") as batches, \
                 mock.patch.object(formal, "create_formal_deep_jobs") as deep_jobs, \
                 mock.patch.object(formal, "collect_trials", return_value=([], [])), \
                 mock.patch.object(formal, "execute_decision") as decision, \
                 mock.patch.object(formal, "merge_formal") as merge, \
                 mock.patch.object(formal, "finalize_formal", return_value={"stage": "formal_complete"}) as finalize:
                result = formal.execute_formal(
                    run_dir, model="test-model", timeout=30, retries=1
                )
            self.assertEqual(batches.call_count, 2)
            deep_jobs.assert_called_once_with(run_dir)
            decision.assert_called_once()
            merge.assert_called_once()
            finalize.assert_called_once_with(run_dir)
            self.assertEqual(result["stage"], "formal_complete")

    def test_prepare_rejects_reused_run_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "stale.json").write_text("{}", encoding="utf-8")
            args = argparse.Namespace(run_dir=str(run_dir))
            with self.assertRaisesRegex(ValueError, "new or empty"):
                formal.prepare_formal(args)

    def test_prepare_forces_unlimited_analysis_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patient = root / "patient.json"
            plan = root / "plan.json"
            patient.write_text("{}", encoding="utf-8")
            plan.write_text("{}", encoding="utf-8")
            args = argparse.Namespace(
                run_dir=str(root / "run"),
                patient=str(patient),
                plan=str(plan),
                db=None,
                mcp_python=None,
                mcp_server=None,
                mcp_transport="streamable-http",
                mcp_url="http://127.0.0.1:8000/mcp",
                max_per_query=5000,
                total_limit=20000,
                batch_size=5,
                portal_delta=None,
            )
            prepared = {
                "all_verified_trials": [{"id": "T1"}, {"id": "T2"}],
                "hard_excluded_trials": [{"id": "T2"}],
                "analysis_candidate_ids": ["T1"],
            }
            with mock.patch.object(formal, "prepare", return_value=prepared) as called:
                state = formal.prepare_formal(args)
            self.assertEqual(called.call_args.kwargs["prefilter_limit"], 0)
            self.assertEqual(called.call_args.kwargs["analysis_limit"], 0)
            self.assertEqual(state["stage"], "gater_pending")
            self.assertEqual(state["recall_count"], 2)

    def test_finalize_cannot_skip_merge_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            formal._save_state(run_dir, {
                "schema_version": "formal-pipeline-state-v1",
                "stage": "gater_pending",
            })
            with self.assertRaisesRegex(ValueError, "not allowed"):
                formal.finalize_formal(run_dir)

    def test_deep_status_requires_exact_id_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jobs = root / "deep_jobs.json"
            batches = root / "deep-batches"
            batches.mkdir()
            jobs.write_text(json.dumps({
                "batches": [{"trials": [{"id": "T1"}, {"id": "T2"}]}],
            }), encoding="utf-8")
            (batches / "deep-batch-001.json").write_text(json.dumps({
                "analyzed_trials": [{"trial_id": "T1"}],
            }), encoding="utf-8")
            audit = formal._deep_status(jobs, batches)
            self.assertFalse(audit["complete"])
            self.assertEqual(audit["missing"], ["T2"])


class ValidationRendererTests(unittest.TestCase):
    def test_validation_artifact_has_no_patient_trial_cards(self):
        payload = {
            "language": "en",
            "run_manifest": {
                "counts": {
                    "recall": 232,
                    "hard_excluded": 0,
                    "gater_completed": 24,
                    "deep_completed": 10,
                    "risk_completed": 10,
                    "efficacy_completed": 10,
                    "evidence_completed": 10,
                    "omitted": 208,
                },
                "quality_gates": {"complete_analysis": False},
                "coverage_audit": {"missing_disposition_ids": ["T25"]},
                "prepared_sha256": "a" * 64,
                "analysis_sha256": "b" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "validation-report.html"
            render_validation_html(payload, output)
            html = output.read_text(encoding="utf-8")
        self.assertIn("Formal workflow validation failed", html)
        self.assertIn("Omitted", html)
        self.assertNotIn('class="trial', html)


if __name__ == "__main__":
    unittest.main()
