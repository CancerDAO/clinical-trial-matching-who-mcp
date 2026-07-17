"""Normalize and merge WHO ICTRP MCP results for the matching pipeline.

The agent calls MCP tools. This module preserves a deterministic boundary between
MCP payloads and the existing gating, scoring, and report contracts.
"""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value[:1] in "[{" and value[-1:] in "]}":
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in re.split(r"[;|]", value) if part.strip()]
    return [value]


def canonical_registry_ids(trial: dict[str, Any]) -> list[str]:
    values = [trial.get("id"), trial.get("trial_id"), trial.get("primary_registry_id"), trial.get("trial_uid")]
    values.extend(item.get("registry_id") if isinstance(item, dict) else item for item in _list(trial.get("registry_ids")))
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = _text(value).upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _country_key(value: Any) -> str:
    aliases = {
        "中国": "china", "mainland china": "china", "usa": "united states",
        "us": "united states", "uk": "united kingdom",
    }
    raw = _text(value).casefold()
    return aliases.get(raw, raw)


def _interventions(value: Any) -> list[str]:
    output: list[str] = []
    for item in _list(value):
        if isinstance(item, dict):
            name = item.get("intervention_name_raw") or item.get("intervention_name_normalized") or item.get("name")
            if name:
                output.append(_text(name))
        else:
            output.extend(_text(part) for part in _list(item))
    return list(dict.fromkeys(item for item in output if item))


def _phases(value: Any) -> list[str]:
    return [_text(item).upper().replace(" ", "_") for item in _list(value) if _text(item)]


def _status(value: Any) -> str:
    return _text(value).upper().replace(" ", "_").replace(",", "")


def normalize_trial(
    trial: dict[str, Any], *, patient_country: str, provenance: str, database_as_of: str = ""
) -> dict[str, Any]:
    """Convert a search hit, get_trial result, or portal row to the old trial shape."""
    source = deepcopy(trial)
    sites = [item for item in _list(source.get("sites")) if isinstance(item, dict)]
    countries = _list(source.get("countries"))
    countries.extend(site.get("country") for site in sites if site.get("country"))
    countries = list(dict.fromkeys(_text(item) for item in countries if _text(item)))
    country_key = _country_key(patient_country)
    patient_sites = [site for site in sites if _country_key(site.get("country")) == country_key]
    ids = canonical_registry_ids(source)
    trial_id = _text(source.get("primary_registry_id") or source.get("id") or source.get("trial_id"))
    if not trial_id and ids:
        trial_id = ids[0]
    criteria = source.get("parsed_criteria") or {"inclusion": [], "exclusion": [], "unknown": [], "raw": ""}
    eligibility = _text(criteria.get("raw") if isinstance(criteria, dict) else "")
    eligibility = eligibility or _text(source.get("eligibility_full") or source.get("eligibility_text"))
    result = {
        **source,
        "id": trial_id,
        "trial_uid": _text(source.get("trial_uid") or trial_id),
        "registry_ids": source.get("registry_ids") or [{"registry_id": item} for item in ids],
        "source": _text(source.get("primary_source") or source.get("source") or provenance),
        "title": _text(source.get("title") or source.get("scientific_title") or source.get("trial_title")),
        "brief_summary": _text(source.get("brief_summary")),
        "phases": _phases(source.get("phase_normalized") or source.get("phases") or source.get("phase")),
        "sponsor": _text(source.get("sponsor_summary") or source.get("sponsor")),
        "interventions": _interventions(source.get("interventions") or source.get("intervention_summary")),
        "overall_status": _status(source.get("recruitment_status_normalized") or source.get("overall_status") or source.get("status")),
        "last_update_date": _text(source.get("last_update_date")),
        "registration_date": _text(source.get("registration_date")),
        "sites": sites,
        "countries": countries,
        "patient_country": patient_country,
        "patient_country_sites": patient_sites,
        "patient_country_site_count": len(patient_sites),
        "domestic_accessible": bool(patient_sites),
        "geography_class": "domestic" if patient_sites else "international",
        "eligibility_full": eligibility,
        "eligibility_excerpt": eligibility[:1200],
        "parsed_criteria": criteria,
        "retrieval_provenance": [provenance],
        "database_as_of": database_as_of or _text(source.get("database_as_of")),
        "source_url": _text(source.get("source_url")),
    }
    if country_key == "china":
        result["patient_country_sites"] = patient_sites
        result["patient_country_site_count"] = len(patient_sites)
    return result


def build_mcp_requests(search_plan: dict[str, Any], patient: dict[str, Any], max_per_query: int = 20) -> dict[str, Any]:
    """Return the MCP calls the orchestrating agent must make."""
    return {
        "metadata": {"tool": "database_metadata", "arguments": {}},
        "local_search": {
            "tool": "execute_search_plan",
            "arguments": {"search_plan": search_plan, "country": "", "max_per_query": max_per_query, "total_limit": 400},
        },
        "detail_policy": {"tool": "get_trial", "argument": "registry_id", "required_for": "all trials retained for gating"},
        "patient_country": _text(patient.get("country")),
    }


def build_portal_delta_contract(database_as_of: str) -> dict[str, Any]:
    """Describe the WHO portal delta without overstating portal semantics."""
    return {
        "registered_after": database_as_of,
        "boundary_type": "registration_date_proxy",
        "database_as_of": database_as_of,
        "warning": (
            "WHO ICTRP portal filtering is based on registration date. It is not a reliable "
            "record-last-update filter; modified older records may be missed."
        ),
    }


def merge_sources(
    local_trials: Iterable[dict[str, Any]], portal_delta_trials: Iterable[dict[str, Any]],
    *, patient: dict[str, Any], database_as_of: str,
) -> list[dict[str, Any]]:
    """Union local and portal rows without letting sparse delta rows erase local detail."""
    country = _text(patient.get("country"))
    merged: list[dict[str, Any]] = []
    id_to_index: dict[str, int] = {}
    refreshable = {"title", "brief_summary", "overall_status", "last_update_date", "registration_date", "source_url"}

    for provenance, rows in (("who_mcp_database", local_trials), ("who_portal_delta", portal_delta_trials)):
        if not isinstance(rows, Iterable) or isinstance(rows, (str, bytes, dict)):
            raise TypeError(f"{provenance} trials must be an iterable of objects")
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError(f"{provenance} trial must be an object, got {type(row).__name__}")
            item = normalize_trial(row, patient_country=country, provenance=provenance, database_as_of=database_as_of)
            ids = canonical_registry_ids(item)
            index = next((id_to_index[value] for value in ids if value in id_to_index), None)
            if index is None:
                index = len(merged)
                merged.append(item)
            else:
                existing = merged[index]
                existing["retrieval_provenance"] = list(dict.fromkeys(existing.get("retrieval_provenance", []) + [provenance]))
                existing["matched_by"] = list(dict.fromkeys(_list(existing.get("matched_by")) + _list(item.get("matched_by"))))
                existing["matched_queries"] = _list(existing.get("matched_queries")) + _list(item.get("matched_queries"))
                existing_ids = {entry.get("registry_id") if isinstance(entry, dict) else entry for entry in _list(existing.get("registry_ids"))}
                for entry in _list(item.get("registry_ids")):
                    registry_id = entry.get("registry_id") if isinstance(entry, dict) else entry
                    if registry_id and registry_id not in existing_ids:
                        existing.setdefault("registry_ids", []).append(entry)
                        existing_ids.add(registry_id)
                if provenance == "who_portal_delta":
                    for key in refreshable:
                        value = item.get(key)
                        if value not in (None, "", [], {}):
                            existing[key] = value
            for registry_id in canonical_registry_ids(merged[index]):
                id_to_index[registry_id] = index
    return merged


def apply_hard_filters(trials: Iterable[dict[str, Any]], search_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Apply only context-safe deterministic filters; defer molecular language to the gater."""
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    lines = int(search_plan.get("treatment_lines") or 0)
    rules = search_plan.get("hard_exclude") or {}
    molecular_rules = [_text(rule) for rule in rules.get("molecular_mismatch") or [] if _text(rule)]
    for source in trials:
        trial = deepcopy(source)
        parsed = trial.get("parsed_criteria") or {}
        inclusion = " ".join(_list(parsed.get("inclusion")) if isinstance(parsed, dict) else []).casefold()
        title = _text(trial.get("title")).casefold()
        reason = ""
        if rules.get("first_line_only") and lines >= 2 and any(
            term in f"{title} {inclusion}" for term in ("first-line only", "first line only", "treatment-naive", "no prior systemic")
        ):
            reason = f"First-line-only trial; patient has completed {lines} lines"
        if molecular_rules:
            trial["hard_filter_warnings"] = [
                f"Gater must evaluate molecular rule in criterion context: {rule}" for rule in molecular_rules
            ]
        if reason:
            trial["exclude_reason"] = reason
            excluded.append(trial)
        else:
            included.append(trial)
    return {"included_trials": included, "excluded_trials": excluded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge WHO MCP search results and WHO portal delta rows")
    parser.add_argument("--local", required=True)
    parser.add_argument("--delta")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    local_payload, metadata, patient, plan = load(args.local), load(args.metadata), load(args.patient), load(args.plan)
    delta = load(args.delta) if args.delta else []
    local = local_payload.get("results", local_payload) if isinstance(local_payload, dict) else local_payload
    merged = merge_sources(local, delta, patient=patient, database_as_of=metadata.get("database_as_of", ""))
    output = {
        **apply_hard_filters(merged, plan), "all_trials": merged, "database_metadata": metadata,
        "database_as_of": metadata.get("database_as_of"),
        "delta_contract": build_portal_delta_contract(metadata.get("database_as_of", "")),
        "source_scope": "WHO ICTRP MCP database + WHO portal registration-date delta",
    }
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
