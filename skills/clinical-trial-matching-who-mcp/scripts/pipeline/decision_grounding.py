"""Reconcile decision paths with validated gater/deep fields."""
from __future__ import annotations

from typing import Any


def ground_decision_path(
    path: dict[str, Any], source: dict[str, Any], *, language: str = "en"
) -> dict[str, Any]:
    gating = source.get("gating") or {}
    risk = source.get("risk_summary") or {}
    efficacy = source.get("efficacy_summary") or {}
    feasibility = source.get("feasibility") or {}
    verdict = str(gating.get("verdict") or "")
    grounded = {
        **path,
        "trial_title": source.get("title") or path.get("trial_title") or "",
        "sponsor": source.get("sponsor") or "",
        "phase": source.get("phase") or [],
        "feasibility_score": feasibility.get("composite"),
        "country_assessment": source.get("country_assessment") or {},
        "patient_country_site_count": source.get("patient_country_site_count") or 0,
        "eligibility_verdict": verdict,
        "requires_eligibility_confirmation": verdict == "conditional",
        "efficacy_snapshot": {
            key: efficacy.get(key)
            for key in ("match_type", "metrics", "evidence_source", "applies_because")
        },
        "vs_soc": efficacy.get("vs_soc") or {"available": False},
        "risks": risk.get("risks") or [],
        "blockers_satisfied": gating.get("blockers_satisfied") or [],
        "blockers_failed": gating.get("blockers_failed") or [],
        "blockers_pending": gating.get("blockers_pending") or [],
    }
    zh = language == "zh-CN"
    if verdict == "conditional":
        prefix = (
            "该试验仅为资格待核实路径，不能视为治疗推荐。"
            if zh else
            "This trial is an eligibility-verification path, not a treatment recommendation."
        )
        rationale = str(path.get("rationale") or "").strip()
        grounded["rationale"] = f"{prefix} {rationale}".strip()
    grounded["consequences_of_skipping"] = (
        "不选择该试验并不等同于失去治疗机会；应与临床团队比较其他试验、标准治疗和支持治疗。"
        if zh else
        "Not pursuing this trial does not imply loss of treatment opportunity; compare other trials, standard care, and supportive care with the clinical team."
    )
    if isinstance(grounded.get("vs_soc"), dict):
        grounded["vs_soc"]["comparison_limitation"] = (
            "除非来源明确为头对头随机研究，否则仅可作跨研究背景参考，不能据此声明优效。"
            if zh else
            "Unless the source is an explicit randomized head-to-head study, this is cross-study context and cannot establish superiority."
        )
    steps = (path.get("estimated_timeline") or {}).get("critical_path_steps") or []
    grounded["estimated_timeline"] = {
        "status": "site_confirmation_required",
        "screening_window": None,
        "earliest_first_dose": None,
        "critical_path_steps": steps,
        "limitation": (
            "Dates cannot be estimated until a recruiting site confirms cohort "
            "availability, screening requirements, and scheduling."
        ),
    }
    return grounded


def ground_decision_report(
    decision: dict[str, Any], analyzed_trials: list[dict[str, Any]], *,
    language: str = "en",
) -> dict[str, Any]:
    sources = {
        str(item.get("trial_id") or "").strip(): item
        for item in analyzed_trials
        if str(item.get("trial_id") or "").strip()
    }
    decision["decision_paths"] = [
        ground_decision_path(
            path, sources[str(path.get("trial_id") or "").strip()],
            language=language,
        )
        for path in decision.get("decision_paths") or []
        if str(path.get("trial_id") or "").strip() in sources
    ]
    decision["clinical_field_policy"] = (
        "Eligibility, efficacy, risk, blockers, and timeline limitations are "
        "deterministically grounded to validated upstream outputs."
    )
    return decision
