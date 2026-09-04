"""Deterministically allocate model work to patient-actionable trials."""
from __future__ import annotations

import os
from typing import Any


PRIORITY_VERSION = "patient-priority-v2"
ACTIVE_STATUSES = {
    "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
}
INACTIVE_STATUSES = {
    "ACTIVE_NOT_RECRUITING", "COMPLETED", "NO_LONGER_RECRUITING",
    "NOT_RECRUITING", "SUSPENDED", "TERMINATED", "WITHDRAWN",
}
IN_COUNTRY_CLASSES = {"domestic_named", "domestic_registry"}


def coverage_mode(value: str | None = None) -> str:
    mode = str(value or os.environ.get("ANALYSIS_COVERAGE") or "patient").strip().casefold()
    if mode not in {"patient", "full"}:
        raise ValueError("ANALYSIS_COVERAGE must be patient or full")
    return mode


def _status(trial: dict[str, Any]) -> str:
    live = str((trial.get("live_registry_verification") or {}).get("status") or "").casefold()
    snapshot = str(trial.get("overall_status") or "").strip().upper().replace(" ", "_")
    if live == "inactive" or snapshot in INACTIVE_STATUSES:
        return "inactive"
    if live == "active" or snapshot in ACTIVE_STATUSES:
        return "active"
    return "unknown"


def annotate_analysis_priority(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag triaged rows without making a new eligibility judgment."""
    annotated: list[dict[str, Any]] = []
    for source in trials:
        trial = dict(source)
        triage = trial.get("recall_triage") or {}
        tier = str(triage.get("tier") or "deferred_audit")
        country_class = str((trial.get("country_assessment") or {}).get("class") or "")
        in_country = (
            country_class in IN_COUNTRY_CLASSES
            or int(trial.get("patient_country_site_count") or 0) > 0
        )
        status = _status(trial)
        if status == "inactive" or tier == "deferred_audit":
            band = "C"
        elif tier == "gater_primary" and (in_country or status == "active"):
            band = "A"
        else:
            band = "B"
        trial["analysis_priority"] = {
            "version": PRIORITY_VERSION,
            "band": band,
            "recall_tier": tier,
            "recruitment_status": status,
            "in_country": in_country,
            "promoted": False,
            "policy": (
                "Patient mode analyzes Band A only. Full mode preserves the historical "
                "Gater workload. Deferred rows remain auditable and are not exclusions."
            ),
        }
        annotated.append(trial)
    return annotated


def promote_empty_band_a(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Promote a small deterministic fallback only when no Band A row exists."""
    if any((row.get("analysis_priority") or {}).get("band") == "A" for row in trials):
        return trials
    try:
        limit = int(os.environ.get("PATIENT_PRIORITY_FALLBACK_LIMIT", "8"))
    except ValueError as exc:
        raise ValueError("PATIENT_PRIORITY_FALLBACK_LIMIT must be an integer") from exc
    if not 0 <= limit <= 40:
        raise ValueError("PATIENT_PRIORITY_FALLBACK_LIMIT must be between 0 and 40")
    ranked = sorted(
        [row for row in trials if (row.get("analysis_priority") or {}).get("band") == "B"],
        key=lambda row: (
            0 if (row.get("analysis_priority") or {}).get("in_country") else 1,
            0 if (row.get("analysis_priority") or {}).get("recruitment_status") == "active" else 1,
            -int((row.get("recall_triage") or {}).get("score") or 0),
            -float((row.get("feasibility") or {}).get("composite") or 0),
            str(row.get("id") or ""),
        ),
    )
    for row in ranked[:limit]:
        priority = dict(row.get("analysis_priority") or {})
        priority.update({"band": "A", "promoted": True})
        row["analysis_priority"] = priority
    return trials


def patient_priority_rows(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in trials
        if (row.get("analysis_priority") or {}).get("band") == "A"
    ]
