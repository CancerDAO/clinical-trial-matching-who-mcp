"""Deterministic patient-country routing for registry retrieval."""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any


COUNTRY_ALIASES = {
    "china": "China",
    "mainland china": "China",
    "pr china": "China",
    "p.r. china": "China",
    "people's republic of china": "China",
    "peoples republic of china": "China",
    "中国": "China",
    "中国大陆": "China",
    "大陆": "China",
    "中华人民共和国": "China",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "美国": "United States",
    "美利坚合众国": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "英国": "United Kingdom",
    "germany": "Germany",
    "德国": "Germany",
    "france": "France",
    "法国": "France",
    "japan": "Japan",
    "日本": "Japan",
    "republic of korea": "Republic of Korea",
    "south korea": "Republic of Korea",
    "韩国": "Republic of Korea",
    "australia": "Australia",
    "澳大利亚": "Australia",
    "canada": "Canada",
    "加拿大": "Canada",
    "singapore": "Singapore",
    "新加坡": "Singapore",
    "india": "India",
    "印度": "India",
}


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", " ", text).casefold()


def canonicalize_country(value: Any) -> str:
    """Return the canonical English registry country, or an empty string."""
    key = _key(value)
    if not key:
        return ""
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    # Standard English country names can pass through without an API/model call.
    if key.isascii() and re.fullmatch(r"[a-z][a-z .'-]*", key):
        return " ".join(part.capitalize() for part in key.split())
    return ""


def resolve_recall_country(
    patient: dict[str, Any], *, plan_country: Any = None,
) -> dict[str, Any]:
    """Resolve global, patient-country, or fixed-country registry scope.

    A model/search-plan country is only a fallback when the patient has no explicit
    country. It can never override an explicit patient country.
    """
    scope = os.environ.get("TRIAL_RECALL_SCOPE", "global").strip().casefold()
    if scope not in {"global", "patient_country", "fixed_country"}:
        raise ValueError(
            "TRIAL_RECALL_SCOPE must be global, patient_country, or fixed_country"
        )
    raw_patient = patient.get("current_country") or patient.get("country") or ""
    configured_default = os.environ.get(
        "TRIAL_RECALL_DEFAULT_COUNTRY", "China"
    ).strip()
    configured_fixed = os.environ.get(
        "TRIAL_RECALL_COUNTRY", configured_default
    ).strip()

    if scope == "global":
        return {
            "scope": scope,
            "patient_country_raw": str(raw_patient),
            "plan_country_candidate": str(plan_country or ""),
            "mcp_country": "",
            "mapping_source": "global_scope",
            "default_country_used": False,
        }

    candidates: list[tuple[str, Any]]
    if scope == "fixed_country":
        candidates = [("configured_fixed_country", configured_fixed)]
    else:
        candidates = [
            ("patient_country", raw_patient),
            ("search_plan_candidate", plan_country),
            ("configured_default_country", configured_default),
        ]
    attempted: list[str] = []
    for source, value in candidates:
        if not str(value or "").strip():
            continue
        attempted.append(str(value))
        canonical = canonicalize_country(value)
        if canonical:
            return {
                "scope": scope,
                "patient_country_raw": str(raw_patient),
                "plan_country_candidate": str(plan_country or ""),
                "mcp_country": canonical,
                "mapping_source": source,
                "default_country_used": source == "configured_default_country",
                "attempted_values": attempted,
            }
    raise ValueError(
        "No MCP-compatible country could be resolved; set "
        "TRIAL_RECALL_COUNTRY or TRIAL_RECALL_DEFAULT_COUNTRY to a canonical English name"
    )


def trial_matches_country(trial: dict[str, Any], country: str) -> bool:
    """Conservatively match structured country/site evidence in sparse delta rows."""
    target = canonicalize_country(country)
    if not target:
        return False
    values: list[Any] = list(trial.get("countries") or [])
    values.extend(
        row.get("country") for row in trial.get("country_records") or []
        if isinstance(row, dict)
    )
    values.extend(
        row.get("country") for row in trial.get("sites") or []
        if isinstance(row, dict)
    )
    return any(canonicalize_country(value) == target for value in values)


def filter_trials_for_country(
    trials: list[dict[str, Any]], country: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not country:
        return list(trials), {
            "country": "", "input_count": len(trials),
            "retained_count": len(trials), "removed_count": 0,
            "policy": "global_scope_no_country_filter",
        }
    retained = [trial for trial in trials if trial_matches_country(trial, country)]
    return retained, {
        "country": country,
        "input_count": len(trials),
        "retained_count": len(retained),
        "removed_count": len(trials) - len(retained),
        "policy": "structured_country_records_or_named_sites",
    }
