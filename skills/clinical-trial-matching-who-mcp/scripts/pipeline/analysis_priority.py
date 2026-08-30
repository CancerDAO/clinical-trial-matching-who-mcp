"""Patient-priority analysis bands: spend model budget on actionable trials.

Band A — full gater + deep analysis. Disease/molecular primary hits that are
either in-country or actively recruiting.
Band B — compact gater only. Basket/overseas/weaker anchors stay auditable
without efficacy papers unless promoted into A.
Band C — no model. Deferred audit, closed studies, and hard exclusions.

Unknown patient facts stay unknown. This module does not infer eligibility.
"""
from __future__ import annotations

import os
from typing import Any

from recall_triage import score_recall_anchor

PRIORITY_VERSION = "patient-priority-v1"
ACTIVE_STATUSES = {
    "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
}
INACTIVE_STATUSES = {
    "ACTIVE_NOT_RECRUITING", "COMPLETED", "NO_LONGER_RECRUITING",
    "NOT_RECRUITING", "SUSPENDED", "TERMINATED", "WITHDRAWN",
}
IN_COUNTRY_CLASSES = {"domestic_named", "domestic_registry"}


def coverage_mode(value: str | None = None) -> str:
    raw = str(value or os.environ.get("ANALYSIS_COVERAGE") or "patient").strip().casefold()
    if raw not in {"patient", "full"}:
        raise ValueError("ANALYSIS_COVERAGE must be patient or full")
    return raw


def _status(trial: dict[str, Any]) -> str:
    live = str((trial.get("live_registry_verification") or {}).get("status") or "").strip().casefold()
    overall = str(trial.get("overall_status") or "").strip().upper().replace(" ", "_")
    if live == "inactive" or overall in INACTIVE_STATUSES:
        return "inactive"
    if live == "active" or overall in ACTIVE_STATUSES:
        return "active"
    return "unknown"


def _trial_id(trial: dict[str, Any]) -> str:
    return str(trial.get("id") or trial.get("trial_id") or "").strip()


def assign_analysis_priority(
    patient: dict[str, Any], trial: dict[str, Any]
) -> dict[str, Any]:
    """Tag one trial with a deterministic A/B/C analysis band."""
    triage = trial.get("recall_triage") or score_recall_anchor(patient, trial)
    tier = str(triage.get("tier") or "")
    country = str((trial.get("country_assessment") or {}).get("class") or "")
    status = _status(trial)
    in_country = country in IN_COUNTRY_CLASSES or int(
        trial.get("patient_country_site_count") or 0
    ) > 0
    reasons: list[str] = list(triage.get("reasons") or [])
    if in_country:
        reasons.append("in_country_access")
    if status == "active":
        reasons.append("recruiting_or_opening")
    if status == "inactive":
        reasons.append("inactive_registry_status")

    if status == "inactive" or tier == "deferred_audit":
        band = "C"
        gater_required = False
        deep_required = False
        gater_mode = "none"
    elif tier == "gater_primary" and (in_country or status == "active"):
        band = "A"
        gater_required = True
        deep_required = True
        gater_mode = "full"
        reasons.append("patient_priority_anchor")
    else:
        band = "B"
        gater_required = True
        deep_required = False
        gater_mode = "compact"
        reasons.append("audit_or_weak_anchor")

    return {
        "version": PRIORITY_VERSION,
        "band": band,
        "gater_required": gater_required,
        "deep_required": deep_required,
        "gater_mode": gater_mode,
        "recall_tier": tier,
        "recruitment_status": status,
        "in_country": in_country,
        "reasons": list(dict.fromkeys(reasons)),
        "promoted": False,
        "policy": (
            "Band A receives full gater and deep analysis. Band B receives compact "
            "gater only. Band C is an auditable non-model disposition, not an eligibility exclusion."
        ),
    }


def annotate_analysis_priority(
    patient: dict[str, Any], trials: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for source in trials:
        trial = dict(source)
        trial["analysis_priority"] = assign_analysis_priority(patient, trial)
        annotated.append(trial)
    return annotated


def _fallback_limit() -> int:
    raw = os.environ.get("PATIENT_DEEP_FALLBACK_LIMIT", "8")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("PATIENT_DEEP_FALLBACK_LIMIT must be an integer") from exc
    if not 0 <= value <= 40:
        raise ValueError("PATIENT_DEEP_FALLBACK_LIMIT must be between 0 and 40")
    return value


def promote_fallback_priority(
    trials: list[dict[str, Any]], *, limit: int | None = None
) -> list[dict[str, Any]]:
    """If no Band A exists, promote the strongest Band B rows so a patient report can still run."""
    if any((trial.get("analysis_priority") or {}).get("band") == "A" for trial in trials):
        return trials
    cap = _fallback_limit() if limit is None else limit
    if cap <= 0:
        return trials
    ranked = sorted(
        [
            trial for trial in trials
            if (trial.get("analysis_priority") or {}).get("band") == "B"
        ],
        key=lambda trial: (
            0 if (trial.get("analysis_priority") or {}).get("in_country") else 1,
            0 if (trial.get("analysis_priority") or {}).get("recruitment_status") == "active" else 1,
            -int((trial.get("recall_triage") or {}).get("score") or 0),
            -float((trial.get("feasibility") or {}).get("composite") or 0),
            _trial_id(trial),
        ),
    )
    for trial in ranked[:cap]:
        priority = dict(trial.get("analysis_priority") or {})
        priority.update({
            "band": "A",
            "gater_required": True,
            "deep_required": True,
            "gater_mode": "full",
            "promoted": True,
        })
        reasons = list(priority.get("reasons") or [])
        reasons.append("promoted_empty_band_a_fallback")
        priority["reasons"] = list(dict.fromkeys(reasons))
        trial["analysis_priority"] = priority
    return trials


def partition_priority(trials: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    bands = {"A": [], "B": [], "C": []}
    for trial in trials:
        band = str((trial.get("analysis_priority") or {}).get("band") or "B")
        bands.setdefault(band, []).append(trial)
    return bands


def deep_required(trial: dict[str, Any], verdict: str = "") -> bool:
    """Deep analysis is required for Band A match/conditional; untagged rows keep the old contract."""
    priority = trial.get("analysis_priority")
    if not isinstance(priority, dict):
        return verdict in {"match", "conditional"} if verdict else True
    if verdict and verdict not in {"match", "conditional"}:
        return False
    return bool(priority.get("deep_required"))


def gater_trials_for_coverage(
    trials: list[dict[str, Any]], mode: str
) -> list[dict[str, Any]]:
    if mode == "full":
        return [
            trial for trial in trials
            if (trial.get("analysis_priority") or {}).get("gater_required")
        ]
    return [
        trial for trial in trials
        if (trial.get("analysis_priority") or {}).get("band") == "A"
    ]
