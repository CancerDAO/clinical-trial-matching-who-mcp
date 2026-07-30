"""Track and merge externally model-executed clinical-analysis batches."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from analysis_contract import (
    JOBS_SCHEMA_VERSION, SCHEMA_VERSION, build_deep_analysis_jobs, load_json,
    validate_analysis_bundle,
)
from io_utils import write_json_atomic


def _batch_files(output_dir: Path, pattern: str = "batch-*.json") -> list[Path]:
    return sorted(output_dir.glob(pattern))


def collect_trials(
    output_dir: Path, pattern: str = "batch-*.json"
) -> tuple[list[dict[str, Any]], list[str]]:
    trials: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for path in _batch_files(output_dir, pattern):
        try:
            payload = load_json(path)
            rows = payload.get("analyzed_trials") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                errors.append(f"{path.name}: analyzed_trials must be a list")
                continue
            for row in rows:
                trial_id = str(row.get("trial_id") or "").strip()
                if not trial_id:
                    errors.append(f"{path.name}: analysis item without trial_id")
                elif trial_id in seen:
                    errors.append(f"{path.name}: duplicate trial_id {trial_id}")
                else:
                    seen.add(trial_id)
                    trials.append(row)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    return trials, errors


def _expected_ids(jobs: dict[str, Any]) -> list[str]:
    return [
        str(trial.get("id") or (trial.get("trial") or {}).get("id") or "")
        for batch in jobs.get("batches") or []
        for trial in batch.get("trials") or []
    ]


def combine_analysis_stages(
    gating_trials: list[dict[str, Any]], deep_trials: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Combine stage outputs into the existing analyzed_trials item shape."""
    gating_by_id = {str(item.get("trial_id") or "").strip(): item for item in gating_trials}
    deep_by_id = {str(item.get("trial_id") or "").strip(): item for item in deep_trials}
    deep_expected = {
        trial_id for trial_id, item in gating_by_id.items()
        if (item.get("gating") or {}).get("verdict") in {"match", "conditional"}
    }
    actual = set(deep_by_id)
    if actual != deep_expected:
        raise ValueError(
            f"Deep analysis coverage mismatch; missing={sorted(deep_expected - actual)[:10]} "
            f"extra={sorted(actual - deep_expected)[:10]}"
        )
    combined = []
    for trial_id, gating_item in gating_by_id.items():
        if trial_id not in deep_expected:
            combined.append(gating_item)
            continue
        deep_item = deep_by_id[trial_id]
        if deep_item.get("gating") and deep_item["gating"] != gating_item.get("gating"):
            raise ValueError(f"{trial_id}: deep output must not change the gater verdict")
        combined.append({**gating_item, **deep_item, "gating": gating_item["gating"]})
    return combined


def create_deep_jobs(
    jobs_path: Path, patient_path: Path, gater_output_dir: Path, out_path: Path,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Materialize deep jobs after complete first-stage gater output exists."""
    jobs = load_json(jobs_path)
    patient = load_json(patient_path)
    gating_trials, errors = collect_trials(gater_output_dir, "gater-batch-*.json")
    if errors:
        raise ValueError("Invalid gater outputs: " + "; ".join(errors[:10]))
    trials = [trial for batch in jobs.get("batches") or [] for trial in batch.get("trials") or []]
    skills_root = Path(jobs["skill_paths"]["trial-gater"]).parent.parent
    deep_jobs = build_deep_analysis_jobs(
        patient, trials, gating_trials, skills_root,
        batch_size=batch_size or int(jobs.get("batch_size") or 5),
    )
    write_json_atomic(out_path, deep_jobs)
    return {"output": str(out_path), "trials": deep_jobs["trial_count"], "validated": True}

def status(jobs_path: Path, output_dir: Path) -> dict[str, Any]:
    jobs = load_json(jobs_path)
    expected = set(_expected_ids(jobs))
    staged = jobs.get("schema_version") == JOBS_SCHEMA_VERSION and bool(
        _batch_files(output_dir, "gater-batch-*.json") or _batch_files(output_dir, "deep-batch-*.json")
    )
    if not staged:
        trials, errors = collect_trials(output_dir)
        actual = {str(item.get("trial_id") or "") for item in trials}
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        return {
            "expected": len(expected), "completed": len(actual & expected),
            "missing_count": len(missing), "missing": missing[:20],
            "unexpected_count": len(unexpected), "unexpected": unexpected[:20],
            "batch_files": len(_batch_files(output_dir)), "errors": errors,
            "complete": actual == expected and not errors,
        }

    gating_trials, gating_errors = collect_trials(output_dir, "gater-batch-*.json")
    gating_actual = {str(item.get("trial_id") or "") for item in gating_trials}
    gating_missing = sorted(expected - gating_actual)
    deep_expected = {
        str(item.get("trial_id") or "") for item in gating_trials
        if (item.get("gating") or {}).get("verdict") in {"match", "conditional"}
    }
    deep_trials, deep_errors = collect_trials(output_dir, "deep-batch-*.json")
    deep_actual = {str(item.get("trial_id") or "") for item in deep_trials}
    deep_missing = sorted(deep_expected - deep_actual)
    gating_unexpected = sorted(gating_actual - expected)
    deep_unexpected = sorted(deep_actual - deep_expected)
    unexpected = sorted(set(gating_unexpected) | set(deep_unexpected))
    errors = gating_errors + deep_errors
    gater_complete = (
        gating_actual == expected and not gating_errors and not gating_unexpected
    )
    deep_complete = (
        deep_actual == deep_expected and not deep_errors and not deep_unexpected
    )
    complete = gater_complete and deep_complete
    return {
        "expected": len(expected),
        "completed": len(gating_actual & expected),
        "missing_count": len(gating_missing),
        "missing": gating_missing[:20],
        "unexpected_count": len(unexpected),
        "unexpected": unexpected[:20],
        "batch_files": len(_batch_files(output_dir, "gater-batch-*.json")) + len(_batch_files(output_dir, "deep-batch-*.json")),
        "errors": errors,
        "stages": {
            "gater": {
                "expected": len(expected),
                "completed": len(gating_actual & expected),
                "missing_count": len(gating_missing),
                "missing": gating_missing[:20],
                "unexpected_count": len(gating_unexpected),
                "unexpected": gating_unexpected[:20],
                "errors": gating_errors,
                "complete": gater_complete,
            },
            "deep": {
                "expected": len(deep_expected),
                "completed": len(deep_actual & deep_expected),
                "missing_count": len(deep_missing),
                "missing": deep_missing[:20],
                "unexpected_count": len(deep_unexpected),
                "unexpected": deep_unexpected[:20],
                "errors": deep_errors,
                "complete": deep_complete,
            },
        },
        "complete": complete,
    }

def merge(
    jobs_path: Path,
    patient_path: Path,
    output_dir: Path,
    decision_path: Path,
    out_path: Path,
    model: str,
    output_language: str,
    deep_output_dir: Path | None = None,
) -> dict[str, Any]:
    jobs = load_json(jobs_path)
    patient = load_json(patient_path)
    if deep_output_dir is None:
        trials, errors = collect_trials(output_dir)
    else:
        gating_trials, gating_errors = collect_trials(output_dir, "gater-batch-*.json")
        deep_trials, deep_errors = collect_trials(deep_output_dir, "deep-batch-*.json")
        errors = gating_errors + deep_errors
        trials = combine_analysis_stages(gating_trials, deep_trials) if not errors else []
    if errors:
        raise ValueError("Invalid batch outputs: " + "; ".join(errors[:10]))
    decision_payload = load_json(decision_path)
    decision = decision_payload.get("decision_report", decision_payload)
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "analysis_provenance": {
            "mode": "llm_subskills",
            "model": model,
            "completed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "output_language": output_language,
            "skills": [
                "trial-gater",
                "trial-risk-annotator",
                "trial-efficacy-contextualizer",
                "decision-synthesizer",
            ],
            "human_review_required": True,
        },
        "analyzed_trials": trials,
        "decision_report": decision,
    }
    expected = _expected_ids(jobs)
    validate_analysis_bundle(bundle, patient, expected)
    write_json_atomic(out_path, bundle)
    return {"output": str(out_path), "trials": len(trials), "validated": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--jobs", required=True)
    status_parser.add_argument("--batch-dir", required=True)
    deep_parser = sub.add_parser("deep-jobs")
    deep_parser.add_argument("--jobs", required=True)
    deep_parser.add_argument("--patient", required=True)
    deep_parser.add_argument("--gater-batch-dir", required=True)
    deep_parser.add_argument("--out", required=True)
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--jobs", required=True)
    merge_parser.add_argument("--patient", required=True)
    merge_parser.add_argument("--batch-dir", required=True)
    merge_parser.add_argument("--deep-batch-dir")
    merge_parser.add_argument("--decision", required=True)
    merge_parser.add_argument("--out", required=True)
    merge_parser.add_argument("--model", required=True)
    merge_parser.add_argument("--output-language", choices=["zh-CN", "en"], required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = status(Path(args.jobs), Path(args.batch_dir))
    elif args.command == "deep-jobs":
        result = create_deep_jobs(
            Path(args.jobs), Path(args.patient), Path(args.gater_batch_dir), Path(args.out)
        )
    else:
        result = merge(
            Path(args.jobs),
            Path(args.patient),
            Path(args.batch_dir),
            Path(args.decision),
            Path(args.out),
            args.model,
            args.output_language,
            Path(args.deep_batch_dir) if args.deep_batch_dir else None,
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
