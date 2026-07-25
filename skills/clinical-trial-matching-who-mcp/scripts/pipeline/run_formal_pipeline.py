"""Stateful formal workflow entry point that prevents skipped analysis stages."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

from analysis_batch_manager import collect_trials, create_deep_jobs, merge, status
from analysis_contract import load_json, report_language
from full_pipeline import finalize, prepare


STATE_NAME = "formal-run-state.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_path(run_dir: Path) -> Path:
    return run_dir / STATE_NAME


def _load_state(run_dir: Path) -> dict[str, Any]:
    path = _state_path(run_dir)
    if not path.exists():
        raise ValueError("Formal run is not prepared; run the prepare command first")
    return load_json(path)


def _save_state(run_dir: Path, state: dict[str, Any]) -> None:
    _write_json(_state_path(run_dir), state)


def _deep_status(jobs_path: Path, batch_dir: Path) -> dict[str, Any]:
    jobs = load_json(jobs_path)
    expected = {
        str(trial.get("id") or "").strip()
        for batch in jobs.get("batches") or []
        for trial in batch.get("trials") or []
    }
    trials, errors = collect_trials(batch_dir, "deep-batch-*.json")
    actual = {str(item.get("trial_id") or "").strip() for item in trials}
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    return {
        "expected": len(expected),
        "completed": len(actual & expected),
        "missing_count": len(missing),
        "missing": missing[:20],
        "unexpected_count": len(unexpected),
        "unexpected": unexpected[:20],
        "errors": errors,
        "complete": actual == expected and not errors,
    }


def prepare_formal(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError("Formal run directory must be new or empty; use a new directory for every run")
    result = prepare(
        patient_path=Path(args.patient),
        plan_path=Path(args.plan),
        out_dir=run_dir,
        database=Path(args.db) if args.db else None,
        server_python=args.mcp_python or "",
        server_script=Path(args.mcp_server) if args.mcp_server else None,
        mcp_transport=args.mcp_transport,
        mcp_url=args.mcp_url or "",
        mcp_api_key=os.environ.get("WHO_MCP_API_KEY", ""),
        max_per_query=args.max_per_query,
        total_limit=args.total_limit,
        prefilter_limit=0,
        analysis_limit=0,
        batch_size=args.batch_size,
        portal_delta_path=Path(args.portal_delta) if args.portal_delta else None,
    )
    state = {
        "schema_version": "formal-pipeline-state-v1",
        "stage": "gater_pending",
        "run_dir": str(run_dir),
        "patient_path": str(Path(args.patient).resolve()),
        "prepared_path": str((run_dir / "prepared.json").resolve()),
        "gater_jobs_path": str((run_dir / "analysis_jobs.json").resolve()),
        "gater_batch_dir": str((run_dir / "gater-batches").resolve()),
        "deep_jobs_path": str((run_dir / "deep_jobs.json").resolve()),
        "deep_batch_dir": str((run_dir / "deep-batches").resolve()),
        "analysis_bundle_path": str((run_dir / "analysis_bundle.json").resolve()),
        "final_dir": str((run_dir / "final").resolve()),
        "recall_count": len(result["all_verified_trials"]),
        "hard_excluded_count": len(result.get("hard_excluded_trials") or []),
        "gater_expected_count": len(result["analysis_candidate_ids"]),
        "next_action": "Complete every gater batch listed in analysis_jobs.json.",
    }
    _save_state(run_dir, state)
    return state


def formal_status(run_dir: Path) -> dict[str, Any]:
    state = _load_state(run_dir)
    jobs = Path(state["gater_jobs_path"])
    gater_dir = Path(state["gater_batch_dir"])
    batch_status = status(jobs, gater_dir)
    result = {**state, "batch_status": batch_status}
    if state["stage"] == "gater_pending":
        result["next_action"] = (
            "Complete all gater batches, then run deep-jobs."
            if not batch_status["complete"]
            else "Run deep-jobs."
        )
    elif state["stage"] == "deep_pending":
        deep_status = _deep_status(
            Path(state["deep_jobs_path"]), Path(state["deep_batch_dir"])
        )
        result["deep_status"] = deep_status
        result["next_action"] = (
            "Complete all deep batches, then run merge."
            if not deep_status["complete"]
            else "Run merge with the decision-synthesizer output."
        )
    return result


def create_formal_deep_jobs(run_dir: Path) -> dict[str, Any]:
    state = _load_state(run_dir)
    if state["stage"] != "gater_pending":
        raise ValueError(f"deep-jobs is not allowed from stage {state['stage']}")
    gater_status = status(Path(state["gater_jobs_path"]), Path(state["gater_batch_dir"]))
    if not gater_status["complete"]:
        raise ValueError(
            f"Cannot create deep jobs: {gater_status['missing_count']} gater result(s) are missing"
        )
    result = create_deep_jobs(
        Path(state["gater_jobs_path"]),
        Path(state["patient_path"]),
        Path(state["gater_batch_dir"]),
        Path(state["deep_jobs_path"]),
    )
    state["stage"] = "deep_pending"
    state["deep_expected_count"] = result["trials"]
    state["next_action"] = "Complete every deep batch listed in deep_jobs.json."
    _save_state(run_dir, state)
    return state


def merge_formal(
    run_dir: Path, decision: Path, model: str, output_language: str
) -> dict[str, Any]:
    state = _load_state(run_dir)
    if state["stage"] != "deep_pending":
        raise ValueError(f"merge is not allowed from stage {state['stage']}")
    deep_status = _deep_status(
        Path(state["deep_jobs_path"]), Path(state["deep_batch_dir"])
    )
    if not deep_status["complete"]:
        raise ValueError(
            f"Cannot merge: {deep_status['missing_count']} deep result(s) are missing"
        )
    result = merge(
        Path(state["gater_jobs_path"]),
        Path(state["patient_path"]),
        Path(state["gater_batch_dir"]),
        decision,
        Path(state["analysis_bundle_path"]),
        model,
        output_language,
        Path(state["deep_batch_dir"]),
    )
    state["stage"] = "analysis_merged"
    state["merged_trial_count"] = result["trials"]
    state["next_action"] = "Run finalize. Do not create patient-facing HTML manually."
    _save_state(run_dir, state)
    return state


def finalize_formal(run_dir: Path) -> dict[str, Any]:
    state = _load_state(run_dir)
    if state["stage"] != "analysis_merged":
        raise ValueError(f"finalize is not allowed from stage {state['stage']}")
    result = finalize(
        prepared_path=Path(state["prepared_path"]),
        analysis_path=Path(state["analysis_bundle_path"]),
        out_dir=Path(state["final_dir"]),
    )
    state["stage"] = "formal_complete" if result["formal_report_ready"] else "validation_failed"
    state["formal_report_ready"] = result["formal_report_ready"]
    state["report_mode"] = result["report_mode"]
    state["run_manifest"] = result["run_manifest"]
    state["next_action"] = (
        "Formal report complete."
        if result["formal_report_ready"]
        else "Inspect validation-report.html and complete the missing work; no formal report was generated."
    )
    _save_state(run_dir, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--patient", required=True)
    prepare_parser.add_argument("--plan", required=True)
    prepare_parser.add_argument("--run-dir", required=True)
    prepare_parser.add_argument(
        "--mcp-transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("WHO_MCP_TRANSPORT", "stdio"),
    )
    prepare_parser.add_argument("--db", default=os.environ.get("WHO_MCP_DB"))
    prepare_parser.add_argument("--mcp-python", default=os.environ.get("WHO_MCP_PYTHON"))
    prepare_parser.add_argument("--mcp-server", default=os.environ.get("WHO_MCP_SERVER"))
    prepare_parser.add_argument("--mcp-url", default=os.environ.get("WHO_MCP_URL"))
    prepare_parser.add_argument("--max-per-query", type=int, default=5000)
    prepare_parser.add_argument("--total-limit", type=int, default=20000)
    prepare_parser.add_argument("--batch-size", type=int, default=5)
    prepare_parser.add_argument("--portal-delta")

    for command in ("status", "deep-jobs", "finalize"):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("--run-dir", required=True)

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--run-dir", required=True)
    merge_parser.add_argument("--decision", required=True)
    merge_parser.add_argument("--model", required=True)
    merge_parser.add_argument("--output-language", choices=("zh-CN", "en"), required=True)

    args = parser.parse_args()
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    if args.command == "prepare":
        result = prepare_formal(args)
    elif args.command == "status":
        result = formal_status(run_dir)
    elif args.command == "deep-jobs":
        result = create_formal_deep_jobs(run_dir)
    elif args.command == "merge":
        patient = load_json(_load_state(run_dir)["patient_path"])
        expected_language = report_language(patient)
        if args.output_language != expected_language:
            raise ValueError(f"output-language must be {expected_language}")
        result = merge_formal(
            run_dir, Path(args.decision), args.model, args.output_language
        )
    else:
        result = finalize_formal(run_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
