"""Deterministically execute every model batch through a configured JSON command."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from analysis_contract import load_json

EXECUTION_CONTRACT = [
    "Use only the patient and trials in this job envelope.",
    "Load and follow every SKILL.md path listed by the job.",
    "Do not select Top-N, omit trials, change trial IDs, or write a patient report.",
    "Return strict JSON only and preserve the requested output schema.",
    "Every input trial ID must appear exactly once in analyzed_trials.",
    "Unknown clinical facts must remain unknown; do not invent eligibility evidence.",
]


def _runner_template() -> list[str]:
    raw = os.environ.get("MODEL_BATCH_RUNNER_JSON", "")
    if not raw:
        if os.environ.get("MODEL_AGENT_COMMAND_JSON"):
            return [
                sys.executable, str(Path(__file__).with_name("cli_model_runner.py")),
                "--input", "{input}", "--output", "{output}",
            ]
        raise ValueError(
            "Set MODEL_BATCH_RUNNER_JSON, or set MODEL_AGENT_COMMAND_JSON for the bundled CLI adapter"
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_BATCH_RUNNER_JSON must be a JSON array") from exc
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError("MODEL_BATCH_RUNNER_JSON must be a non-empty array of strings")
    if not any("{input}" in item for item in value) or not any("{output}" in item for item in value):
        raise ValueError("MODEL_BATCH_RUNNER_JSON must contain {input} and {output}")
    return value


def _ids(batch: dict[str, Any]) -> set[str]:
    return {
        str(trial.get("id") or "").strip()
        for trial in batch.get("trials") or []
        if str(trial.get("id") or "").strip()
    }


def _validate_batch_output(batch: dict[str, Any], output: Path) -> None:
    payload = load_json(output)
    rows = payload.get("analyzed_trials") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{output.name}: analyzed_trials must be a list")
    actual = [str(row.get("trial_id") or "").strip() for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != _ids(batch):
        raise ValueError(
            f"{output.name}: trial ID coverage mismatch; "
            f"missing={sorted(_ids(batch) - set(actual))[:10]} "
            f"extra={sorted(set(actual) - _ids(batch))[:10]}"
        )


def _run_envelope(
    envelope: dict[str, Any], input_path: Path, output_path: Path, *,
    retries: int, timeout: float,
) -> None:
    input_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    command = [
        item.replace("{input}", str(input_path)).replace("{output}", str(output_path))
        for item in _runner_template()
    ]
    last_error = ""
    for attempt in range(retries + 1):
        if output_path.exists():
            output_path.unlink()
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True, timeout=timeout,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"runner exit {completed.returncode}: "
                    f"{(completed.stderr or completed.stdout)[-1000:]}"
                )
            if not output_path.exists():
                raise RuntimeError("runner did not create the requested output file")
            return
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Model runner failed after {retries + 1} attempts: {last_error}")


def execute_batches(
    jobs_path: Path, output_dir: Path, *, output_prefix: str,
    retries: int = 2, timeout: float = 1800,
) -> dict[str, Any]:
    jobs = load_json(jobs_path)
    input_dir = output_dir.parent / "runner-inputs"
    completed = skipped = 0
    for batch in jobs.get("batches") or []:
        batch_id = str(batch.get("batch_id") or "")
        number_match = batch_id.rsplit("-", 1)[-1]
        output = output_dir / f"{output_prefix}-{number_match}.json"
        if output.exists():
            _validate_batch_output(batch, output)
            skipped += 1
            continue
        envelope = {
            "schema_version": "deterministic-model-job-v1",
            "execution_contract": EXECUTION_CONTRACT,
            "job": batch,
            "skill_paths": jobs.get("skill_paths") or {},
            "required_output": {
                "path": str(output),
                "format": "JSON object with analyzed_trials",
                "expected_trial_ids": sorted(_ids(batch)),
            },
        }
        _run_envelope(
            envelope, input_dir / f"{output_prefix}-{number_match}-input.json", output,
            retries=retries, timeout=timeout,
        )
        _validate_batch_output(batch, output)
        completed += 1
    return {
        "expected_batches": len(jobs.get("batches") or []),
        "executed_batches": completed,
        "resumed_batches": skipped,
        "complete": completed + skipped == len(jobs.get("batches") or []),
    }


def execute_decision(
    *, patient_path: Path, analysis_path: Path, skill_path: Path,
    output_path: Path, retries: int = 2, timeout: float = 1800,
) -> dict[str, Any]:
    envelope = {
        "schema_version": "deterministic-model-job-v1",
        "execution_contract": EXECUTION_CONTRACT,
        "job": {
            "stage": "decision",
            "patient": load_json(patient_path),
            "analyzed_trials": load_json(analysis_path).get("analyzed_trials") or [],
            "skill_path": str(skill_path),
        },
        "required_output": {
            "path": str(output_path),
            "format": "JSON object containing decision_report",
        },
    }
    _run_envelope(
        envelope, output_path.parent / "runner-inputs" / "decision-input.json",
        output_path, retries=retries, timeout=timeout,
    )
    payload = load_json(output_path)
    if not isinstance(payload.get("decision_report", payload), dict):
        raise ValueError("Decision runner output must be an object")
    return {"output": str(output_path), "complete": True}
