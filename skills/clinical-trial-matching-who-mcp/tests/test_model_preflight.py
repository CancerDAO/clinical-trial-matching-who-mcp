import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))

from model_preflight import apply_model_routes, run_model_preflight
from run_formal_pipeline import _apply_prepare_model_args


class ModelPreflightTests(unittest.TestCase):
    def test_prepare_cli_models_become_stage_specific_configuration(self):
        args = type("Args", (), {
            "model_provider": "minimax",
            "model_base_url": "https://api.minimaxi.com/v1",
            "gater_model": "fast-gater",
            "deep_model": "strong-deep",
            "decision_model": "strong-decision",
            "translation_model": "fast-translation",
        })()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_apply_prepare_model_args(args))
            self.assertEqual(os.environ["MODEL_PROVIDER"], "minimax")
            self.assertEqual(os.environ["MODEL_BASE_URL"], "https://api.minimaxi.com/v1")
            self.assertEqual(os.environ["DEEP_MODEL_NAME"], "strong-deep")
            self.assertEqual(os.environ["TRANSLATION_MODEL_NAME"], "fast-translation")

    def test_preflight_records_only_successful_non_secret_routes(self):
        with mock.patch("model_preflight.configured_stage", return_value=True), mock.patch(
            "model_preflight.probe_stage",
            side_effect=lambda stage: {
                "provider": "minimax", "model": f"model-{stage}",
                "protocol": "openai-chat", "latency_ms": 10,
                "json_contract": True,
            },
        ):
            result = run_model_preflight()
        self.assertEqual(set(result["routes"]), {"gater", "deep", "decision", "translation"})
        self.assertNotIn("api_key", str(result).casefold())

    def test_required_stage_without_configuration_fails_before_retrieval(self):
        with mock.patch(
            "model_preflight.configured_stage", side_effect=lambda stage: stage != "deep"
        ), mock.patch("model_preflight.probe_stage", return_value={}):
            with self.assertRaisesRegex(ValueError, "required stage: deep"):
                run_model_preflight()

    def test_apply_routes_sets_stage_specific_non_secret_configuration(self):
        routing = {"routes": {"gater": {
            "provider": "openai-compatible",
            "model": "fast-gater",
            "base_url": "https://models.example.test/v1",
            "protocol": "openai-chat",
        }}}
        with mock.patch.dict(os.environ, {}, clear=True):
            models = apply_model_routes(routing)
            self.assertEqual(models, {"gater": "fast-gater"})
            self.assertEqual(os.environ["GATER_MODEL_PROVIDER"], "openai-compatible")
            self.assertEqual(os.environ["GATER_MODEL_NAME"], "fast-gater")
            self.assertEqual(
                os.environ["GATER_MODEL_BASE_URL"], "https://models.example.test/v1"
            )
            self.assertNotIn("GATER_MODEL_API_KEY", os.environ)

    def test_auto_selection_stops_after_first_passing_candidate(self):
        def probe(stage, model=""):
            result = {
                "provider": "minimax", "model": model,
                "protocol": "openai-chat",
                "latency_ms": 20 if model == "fast" else 80,
                "json_contract": True,
            }
            if stage == "translation":
                result["characters_per_minute"] = 4000 if model == "fast" else 1000
            return result

        with mock.patch.dict(
            os.environ,
            {"MODEL_CANDIDATES": "slow,fast", "MODEL_SELECTION_MAX_CALLS": "8"},
            clear=True,
        ), mock.patch("model_preflight.probe_stage", side_effect=probe):
            result = run_model_preflight(auto_select=True)
        self.assertEqual(result["selection_mode"], "automatic")
        self.assertTrue(all(route["model"] == "slow" for route in result["routes"].values()))
        self.assertEqual(len(result["selection_audit"]["deep"]), 1)

    def test_auto_selection_tries_the_fallback_only_after_failure(self):
        calls = []

        def probe(stage, model=""):
            calls.append((stage, model))
            if model == "first":
                raise RuntimeError("not available")
            return {
                "provider": "minimax", "model": model,
                "protocol": "openai-chat", "latency_ms": 20,
                "json_contract": True, "characters_per_minute": 3000,
            }

        with mock.patch.dict(
            os.environ,
            {"MODEL_CANDIDATES": "first,second", "MODEL_SELECTION_MAX_CALLS": "8"},
            clear=True,
        ), mock.patch("model_preflight.probe_stage", side_effect=probe):
            result = run_model_preflight(auto_select=True)
        self.assertTrue(all(route["model"] == "second" for route in result["routes"].values()))
        self.assertEqual(calls[:2], [("gater", "first"), ("gater", "second")])

    def test_auto_selection_discovers_models_when_candidates_are_missing(self):
        with mock.patch.dict(
            os.environ,
            {
                "MODEL_PROVIDER": "glm",
                "GLM_API_KEY": "test-key",
                "MODEL_SELECTION_MAX_CALLS": "4",
                "MODEL_SELECTION_MAX_CANDIDATES": "1",
            },
            clear=True,
        ), mock.patch(
            "model_preflight.discover_models", return_value=["discovered-model"]
        ) as discover, mock.patch(
            "model_preflight.probe_stage",
            side_effect=lambda stage, model="": {
                "provider": "openai-compatible", "model": model,
                "protocol": "openai-chat", "latency_ms": 10,
                "json_contract": True,
            },
        ):
            result = run_model_preflight(auto_select=True)
        self.assertEqual(discover.call_count, 0)
        self.assertEqual(result["routes"]["gater"]["model"], "glm-4.7-flash")


if __name__ == "__main__":
    unittest.main()
