"""Cancer-agnostic deterministic triage between recall and model analysis."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from disease_concepts import resolve_disease_terms, strip_clinical_source_annotation


TRIAGE_VERSION = "recall-anchor-triage-v1"
_GENERIC_DISEASE_TERMS = {
    "cancer", "malignancy", "malignant tumor", "neoplasm", "solid tumor",
    "advanced solid tumor", "metastatic solid tumor",
}


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " | ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " | ".join(_text(item) for item in value.values())
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", " ", _text(value).casefold()).strip()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    phrase = _canonical(phrase)
    return bool(phrase and re.search(rf"(?:^| )({re.escape(phrase)})(?: |$)", haystack))


def _patient_molecular_anchors(patient: dict[str, Any]) -> list[str]:
    values: list[Any] = list(patient.get("mutations") or [])
    values.extend((patient.get("biomarkers_known") or {}).keys())
    anchors: list[str] = []
    for value in values:
        entity, _ = strip_clinical_source_annotation(value)
        normalized = _canonical(entity)
        normalized = re.sub(r"\b(?:mutation|mutated|positive|status)\b", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized and normalized not in {"unknown", "not tested", "negative"}:
            anchors.append(normalized)
    return list(dict.fromkeys(anchors))


def _trial_search_text(trial: dict[str, Any]) -> str:
    values = [
        trial.get("title"), trial.get("scientific_title"), trial.get("brief_summary"),
        trial.get("disease_text"), trial.get("intervention_summary"),
        trial.get("interventions"), trial.get("eligibility_full"),
        trial.get("eligibility_excerpt"), trial.get("parsed_criteria"),
        trial.get("matched_queries"),
    ]
    return _canonical(values)


def _live_status(trial: dict[str, Any]) -> str:
    live = trial.get("live_registry_verification") or {}
    return str(live.get("status") or "unknown").strip().casefold()


def score_recall_anchor(patient: dict[str, Any], trial: dict[str, Any]) -> dict[str, Any]:
    disease = resolve_disease_terms(
        patient.get("cancer_type"), patient.get("search_terms") or {}
    )
    disease_terms = [
        term for term in disease.get("english_aliases") or []
        if _canonical(term) not in _GENERIC_DISEASE_TERMS
    ]
    molecular_terms = _patient_molecular_anchors(patient)
    text = _trial_search_text(trial)
    disease_matches = [term for term in disease_terms if _contains_phrase(text, term)]
    molecular_matches = [term for term in molecular_terms if _contains_phrase(text, term)]
    matched_by = [str(value) for value in trial.get("matched_by") or [] if str(value).strip()]
    matched_queries = _canonical(trial.get("matched_queries") or [])
    query_has_disease = any(_contains_phrase(matched_queries, term) for term in disease_terms)
    query_has_molecular = any(_contains_phrase(matched_queries, term) for term in molecular_terms)

    score = 0
    reasons: list[str] = []
    if disease_matches:
        score += 4
        reasons.append("direct_disease_anchor")
    if molecular_matches:
        score += 4
        reasons.append("exact_molecular_anchor")
    if query_has_disease and (query_has_molecular or not molecular_terms):
        score += 2
        reasons.append("patient_specific_query_anchor")
    elif query_has_disease or query_has_molecular:
        score += 1
        reasons.append("partial_query_anchor")
    if int(trial.get("patient_country_site_count") or 0) > 0:
        score += 1
        reasons.append("patient_country_site")
    if len(matched_by) >= 2:
        score += 1
        reasons.append("multiple_retrieval_branches")

    live_status = _live_status(trial)
    weak_anchor = not disease_matches and not molecular_matches and not (
        query_has_disease or query_has_molecular
    )
    if disease_matches and (molecular_matches or not molecular_terms):
        tier = "gater_primary"
    elif score >= 6:
        tier = "gater_primary"
    elif disease_matches or molecular_matches or score >= 3:
        tier = "gater_secondary"
    else:
        tier = "deferred_audit"
    if live_status == "unknown" and weak_anchor:
        tier = "deferred_audit"
        reasons.append("unknown_registry_status_with_weak_anchor")
    if tier == "deferred_audit" and "low_patient_specific_anchor" not in reasons:
        reasons.append("low_patient_specific_anchor")

    return {
        "version": TRIAGE_VERSION,
        "tier": tier,
        "score": score,
        "reasons": reasons,
        "disease_matches": disease_matches,
        "molecular_matches": molecular_matches,
        "matched_branch_count": len(matched_by),
        "live_registry_status": live_status,
        "policy": (
            "Deferred means insufficient deterministic patient-specific anchoring for "
            "immediate model analysis; it is not an eligibility exclusion."
        ),
    }


def stratify_recall_candidates(
    patient: dict[str, Any], trials: list[dict[str, Any]]
) -> dict[str, Any]:
    tiers: dict[str, list[dict[str, Any]]] = {
        "gater_primary": [], "gater_secondary": [], "deferred_audit": [],
    }
    reason_counts: Counter[str] = Counter()
    for source in trials:
        trial = dict(source)
        audit = score_recall_anchor(patient, trial)
        trial["recall_triage"] = audit
        tiers[audit["tier"]].append(trial)
        reason_counts.update(audit["reasons"])
    return {
        **tiers,
        "audit": {
            "version": TRIAGE_VERSION,
            "input_count": len(trials),
            "gater_primary_count": len(tiers["gater_primary"]),
            "gater_secondary_count": len(tiers["gater_secondary"]),
            "deferred_audit_count": len(tiers["deferred_audit"]),
            "reason_counts": dict(sorted(reason_counts.items())),
            "disposition_complete": sum(len(rows) for rows in tiers.values()) == len(trials),
        },
    }
