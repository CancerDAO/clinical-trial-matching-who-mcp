"""Low-cost model capability checks and stage routing for formal runs."""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from contextlib import contextmanager
from typing import Any

from model_api_runner import (
    _assert_complete_response,
    _configuration,
    _json_payload,
    _post,
    _request,
    _response_text,
    _stage_value,
)


STAGES = ("gater", "deep", "decision", "translation")
CANDIDATE_POOLS_REVIEWED_AT = "2026-08-18"
NON_TEXT_MARKERS = (
    "embedding", "rerank", "moderation", "image", "audio", "speech", "tts",
)
DEFAULT_CANDIDATE_POOLS = {
    "openai": {
        "gater": ["gpt-5-nano", "gpt-5-mini"],
        "deep": ["gpt-5-mini", "gpt-5.1"],
        "decision": ["gpt-5-mini", "gpt-5.1"],
        "translation": ["gpt-5-nano", "gpt-5-mini"],
    },
    "anthropic": {
        "gater": ["claude-haiku-4-5-20251001", "claude-sonnet-5"],
        "deep": ["claude-sonnet-5", "claude-opus-5"],
        "decision": ["claude-sonnet-5", "claude-opus-5"],
        "translation": ["claude-haiku-4-5-20251001", "claude-sonnet-5"],
    },
    "minimax": {
        "gater": ["MiniMax-M3", "MiniMax-M2.7"],
        "deep": ["MiniMax-M3", "MiniMax-M2.7"],
        "decision": ["MiniMax-M3", "MiniMax-M2.7"],
        "translation": ["MiniMax-M3", "MiniMax-M2.7"],
    },
    "glm": {
        "gater": ["glm-4.7-flash", "glm-4.7"],
        "deep": ["glm-5-turbo", "glm-5.2"],
        "decision": ["glm-5-turbo", "glm-5.2"],
        "translation": ["glm-4.7-flash", "glm-4.7"],
    },
}


def configured_stage(stage: str) -> bool:
    return bool(_stage_value(stage, "MODEL_PROVIDER") and _stage_value(stage, "MODEL_NAME"))


@contextmanager
def _temporary_stage_model(stage: str, model: str):
    name = f"{stage.upper()}_MODEL_NAME"
    previous = os.environ.get(name)
    os.environ[name] = model
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def probe_stage(stage: str, model_override: str = "") -> dict[str, Any]:
    if model_override:
        with _temporary_stage_model(stage, model_override):
            return probe_stage(stage)
    provider_name, provider, model, base_url, key = _configuration(stage)
    protocol = _stage_value(stage, "MODEL_API_PROTOCOL") or provider.protocol
    translation_sources = [
        "Confirm disease histology and the molecular cohort with the study center.",
        "Prior systemic therapy and the required washout period need confirmation.",
        "Current liver, renal, cardiac, and hematologic function are not documented.",
        "The trial includes advanced solid tumors with the specified biomarker.",
        "Recruitment status and an available slot must be verified directly.",
        "Performance status must meet the protocol requirement before enrollment.",
        "Concurrent anticancer treatment may require interruption before screening.",
        "The available publication is early-phase evidence without head-to-head comparison.",
        "A named center is recorded in the patient country, but availability may change.",
        "Final eligibility requires review of the complete protocol by the study team.",
    ]
    translation_input = [
        {"id": f"u{index}", "source": source}
        for index, source in enumerate(translation_sources)
    ]
    prompts = {
        "gater": (
            'Return exactly {"analyzed_trials":[{"trial_id":"SYNTHETIC-1",'
            '"gating":{"verdict":"conditional","confidence":0.8}}]}. '
            "Do not add commentary."
        ),
        "deep": (
            'Return exactly {"analyzed_trials":[{"trial_id":"SYNTHETIC-1",'
            '"risk_annotation":{},"efficacy_context":{}}]}. Do not add commentary.'
        ),
        "decision": (
            'Return exactly {"decision_paths":[{"trial_id":"SYNTHETIC-1",'
            '"priority":1}]}. Do not add commentary.'
        ),
        "translation": (
            "Translate every source into concise Simplified Chinese and return exactly "
            '{"translations":[{"id":"u0","text":"..."}]}. Preserve every id, '
            "omit none, and add no commentary. INPUT: "
            + json.dumps(translation_input, ensure_ascii=False)
        ),
    }
    prompt = prompts[stage]
    started = time.perf_counter()
    url, headers, body = _request(
        provider_name, protocol, base_url, key, model, prompt, stage=stage,
    )
    response = _post(url, headers, body)
    _assert_complete_response(protocol, response)
    parsed = _json_payload(_response_text(protocol, response))
    if stage == "translation":
        rows = parsed.get("translations") or []
        returned = {
            str(row.get("id") or ""): str(row.get("text") or "")
            for row in rows if isinstance(row, dict)
        }
        valid = set(returned) == {row["id"] for row in translation_input}
        valid = valid and all(
            any("\u3400" <= character <= "\u9fff" for character in text)
            for text in returned.values()
        )
    elif stage == "decision":
        paths = parsed.get("decision_paths") or []
        valid = bool(paths and paths[0].get("trial_id") == "SYNTHETIC-1")
    else:
        rows = parsed.get("analyzed_trials") or []
        valid = bool(rows and rows[0].get("trial_id") == "SYNTHETIC-1")
        if valid and stage == "gater":
            gating = rows[0].get("gating") or {}
            valid = gating.get("verdict") == "conditional" and isinstance(
                gating.get("confidence"), (int, float)
            )
        if valid and stage == "deep":
            valid = isinstance(rows[0].get("risk_annotation"), dict) and isinstance(
                rows[0].get("efficacy_context"), dict
            )
    if not valid:
        raise RuntimeError(f"{stage} model failed the preflight output contract")
    latency_ms = round((time.perf_counter() - started) * 1000)
    result = {
        "provider": provider_name,
        "model": model,
        "base_url": base_url,
        "protocol": protocol,
        "latency_ms": latency_ms,
        "json_contract": True,
        "simplified_chinese": True if stage == "translation" else None,
    }
    if stage == "translation":
        source_characters = sum(len(row["source"]) for row in translation_input)
        characters_per_minute = round(source_characters * 60_000 / latency_ms)
        concurrency = max(1, min(int(os.environ.get("TRANSLATION_MODEL_CONCURRENCY", "6")), 8))
        # Concurrent requests rarely scale linearly; use a conservative 70%
        # efficiency factor and expose the estimate instead of making it a gate.
        effective_throughput = max(1, characters_per_minute * concurrency * 0.7)
        result["benchmark_units"] = len(translation_input)
        result["benchmark_characters"] = source_characters
        result["units_per_minute"] = round(len(translation_input) * 60_000 / latency_ms, 1)
        result["characters_per_minute"] = characters_per_minute
        result["estimated_minutes_per_100k_characters"] = round(
            100_000 / effective_throughput, 1
        )
        result["estimate_concurrency"] = concurrency
    return result


def _stage_provider(stage: str) -> str:
    with _temporary_stage_model(stage, "__provider_lookup__"):
        provider_name, _, _, _, _ = _configuration(stage)
    return provider_name


def _candidate_values(stage: str) -> list[str]:
    raw = (
        os.environ.get(f"{stage.upper()}_MODEL_CANDIDATES", "").strip()
        or os.environ.get("MODEL_CANDIDATES", "").strip()
    )
    if not raw:
        return list((DEFAULT_CANDIDATE_POOLS.get(_stage_provider(stage)) or {}).get(stage) or [])
    if raw.startswith("["):
        values = json.loads(raw)
        if not isinstance(values, list):
            raise ValueError("MODEL_CANDIDATES JSON must be an array")
    else:
        values = raw.split(",")
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def discover_models(stage: str) -> list[str]:
    """Use a provider model-list endpoint when no explicit candidate pool exists."""
    with _temporary_stage_model(stage, "__model_discovery__"):
        provider_name, _, _, base_url, key = _configuration(stage)
    headers = {"Accept": "application/json"}
    if provider_name == "anthropic":
        headers.update({
            "x-api-key": key,
            "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
        })
    else:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
    timeout = float(os.environ.get("MODEL_SELECTION_TIMEOUT_SECONDS", "60"))
    with urllib.request.urlopen(
        request, timeout=timeout, context=ssl.create_default_context(),
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Provider model discovery did not return a data array")
    models = []
    for row in rows:
        model = str(row.get("id") or "").strip() if isinstance(row, dict) else ""
        if model and not any(marker in model.casefold() for marker in NON_TEXT_MARKERS):
            models.append(model)
    return list(dict.fromkeys(models))


def _select_stage(stage: str, candidates: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts = []
    for model in candidates:
        try:
            result = probe_stage(stage, model)
            attempts.append({"model": model, "passed": True, "latency_ms": result["latency_ms"]})
            if stage == "translation":
                attempts[-1]["characters_per_minute"] = result.get("characters_per_minute")
                attempts[-1]["estimated_minutes_per_100k_characters"] = result.get(
                    "estimated_minutes_per_100k_characters"
                )
            return result, attempts
        except Exception as exc:
            attempts.append({"model": model, "passed": False, "error": str(exc)[:300]})
    raise RuntimeError(f"No candidate model passed the {stage} preflight contract")


def run_model_preflight(*, auto_select: bool = False) -> dict[str, Any]:
    routes: dict[str, Any] = {}
    audits: dict[str, Any] = {}
    total_budget = max(1, int(os.environ.get("MODEL_SELECTION_MAX_CALLS", "12")))
    per_stage = max(1, int(os.environ.get("MODEL_SELECTION_MAX_CANDIDATES", "3")))
    for stage in STAGES:
        if not auto_select and configured_stage(stage):
            routes[stage] = probe_stage(stage)
            continue
        candidates = _candidate_values(stage) if auto_select else []
        if auto_select and not candidates:
            candidates = discover_models(stage)
        candidates = candidates[:min(per_stage, total_budget)]
        if candidates:
            selected, attempts = _select_stage(stage, candidates)
            routes[stage] = selected
            audits[stage] = attempts
            total_budget -= len(attempts)
        elif configured_stage(stage):
            routes[stage] = probe_stage(stage)
        elif stage != "translation":
            raise ValueError(f"No model configuration is available for required stage: {stage}")
        if total_budget <= 0 and stage != STAGES[-1]:
            raise RuntimeError("MODEL_SELECTION_MAX_CALLS was exhausted before all stages were routed")
    return {
        "schema_version": "model-routing-v1",
        "candidate_pools_reviewed_at": CANDIDATE_POOLS_REVIEWED_AT,
        "routes": routes,
        "selection_mode": "automatic" if auto_select else "configured",
        "selection_audit": audits,
    }


def apply_model_routes(routing: dict[str, Any]) -> dict[str, str]:
    """Apply non-secret, preflighted routing to the current executor process."""
    models: dict[str, str] = {}
    for stage, route in (routing.get("routes") or {}).items():
        prefix = str(stage).upper()
        for suffix, key in (
            ("MODEL_PROVIDER", "provider"),
            ("MODEL_NAME", "model"),
            ("MODEL_BASE_URL", "base_url"),
            ("MODEL_API_PROTOCOL", "protocol"),
        ):
            value = str(route.get(key) or "").strip()
            if value:
                __import__("os").environ[f"{prefix}_{suffix}"] = value
        if route.get("model"):
            models[str(stage)] = str(route["model"])
    return models
