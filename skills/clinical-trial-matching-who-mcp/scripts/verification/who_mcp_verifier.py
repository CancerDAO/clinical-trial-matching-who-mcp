"""Verify, enrich, and post-detail-deduplicate WHO MCP trial records."""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


def _key(value: Any) -> str:
    aliases = {"中国": "china", "mainland china": "china", "usa": "united states", "us": "united states"}
    raw = str(value or "").strip().casefold()
    return aliases.get(raw, raw)


def _status(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace(",", "")


def _phases(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [part.strip() for part in str(value).replace("|", ";").split(";")]
    return [str(item).strip().upper().replace(" ", "_") for item in values if str(item).strip()]


_STANDARD_REGISTRY_ID = re.compile(
    r"^(?:NCT\d{8}|CHICTR[\w-]+|CTIS20\d{2}-\d{6}-\d{2}(?:-00)?|"
    r"ACTRN\d+|ISRCTN\d+|DRKS\d+|JPRN-[\w-]+|UMIN\d+|KCT\d+|"
    r"TCTR\d+|IRCT[\w-]+|PACTR[\w-]+|NL-[\w-]+|CTRI/[\w/-]+|"
    r"EUCTR[\w-]+|U1111-\d{4}-\d{4})$",
    re.I,
)


def _ids(trial: dict[str, Any]) -> list[str]:
    values = [
        trial.get("trial_uid"), trial.get("primary_registry_id"),
        trial.get("id"), trial.get("trial_id"),
    ]
    for item in trial.get("registry_ids") or []:
        value = item.get("registry_id") if isinstance(item, dict) else item
        is_primary = (
            isinstance(item, dict)
            and (
                item.get("is_primary") in {1, True, "1", "true"}
                or str(item.get("id_type") or "").casefold() in {"main_id", "primary"}
            )
        )
        if is_primary or _STANDARD_REGISTRY_ID.fullmatch(
            re.sub(r"\s+", "", str(value or ""))
        ):
            values.append(value)
    output: list[str] = []
    for value in values:
        key = re.sub(r"\s+", "", str(value or "")).upper()
        if not key:
            continue
        output.append(key)
        eu = re.sub(r"^CTIS", "", key)
        if re.fullmatch(r"20\d{2}-\d{6}-\d{2}(?:-00)?", eu):
            output.append("CTIS_CORE:" + re.sub(r"-00$", "", eu))
    return list(dict.fromkeys(output))

def _detail_rows(details: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(details, dict) and "details" in details:
        details = details["details"]
    if isinstance(details, dict):
        details = list(details.values())
    return [detail for detail in details if isinstance(detail, dict) and detail.get("found", True)]


def detail_lookups(details: list[dict[str, Any]] | dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    exact: dict[str, dict[str, Any]] = {}
    aliases: dict[str, dict[str, Any]] = {}
    for detail in _detail_rows(details):
        for value in (detail.get("trial_uid"), detail.get("primary_registry_id")):
            if value:
                exact[str(value).strip().upper()] = detail
        for registry_id in _ids(detail):
            aliases.setdefault(registry_id, detail)
    return exact, aliases


def detail_lookup(details: list[dict[str, Any]] | dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Backward-compatible alias lookup used by existing callers and tests."""
    _, aliases = detail_lookups(details)
    return aliases


def _has_named_site(site: dict[str, Any]) -> bool:
    return any(str(site.get(field) or "").strip() for field in ("site_name", "facility", "city", "province"))


def _country_values(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = re.split(r"\s*[|;,]\s*", str(value or ""))
    return [str(item).strip() for item in values if str(item).strip()]


def verify_one(trial: dict[str, Any], detail: dict[str, Any] | None, patient: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(trial)
    if not detail:
        result["verification"] = {"status": "unverified", "source": "WHO ICTRP MCP", "reason": "No get_trial response supplied"}
        return result

    patient_country = _key(patient.get("country"))
    sites = detail.get("sites") or []
    country_records = detail.get("country_records") or []
    patient_sites = [
        site for site in sites
        if _key(site.get("country")) == patient_country and _has_named_site(site)
    ]
    if "country_records" in detail:
        patient_location_records = [
            record for record in country_records if _key(record.get("country")) == patient_country
        ]
    else:
        # Backward compatibility for schema v2 country-only site rows.
        patient_location_records = [
            site for site in sites if _key(site.get("country")) == patient_country
        ]
    # Some ICTRP records expose only a country list when site rows are incomplete.
    # Keep this as country-only evidence; never promote it to a named centre.
    if not patient_location_records:
        patient_location_records = [
            {"country": country, "evidence_type": "trial_country_list"}
            for country in _country_values(detail.get("countries"))
            if _key(country) == patient_country
        ]
    interventions = []
    for item in detail.get("interventions") or []:
        name = item.get("intervention_name_raw") or item.get("intervention_name_normalized") or item.get("name")
        if name:
            interventions.append(name)
    title = detail.get("title") or detail.get("scientific_title") or result.get("title", "")
    mismatches = []
    if result.get("title") and title and result["title"].strip().casefold() != title.strip().casefold():
        mismatches.append("Search title differs from canonical MCP detail")
    geography_class = "domestic" if patient_sites else "domestic_unverified" if patient_location_records else "international"
    result.update({
        "trial_uid": detail.get("trial_uid") or result.get("trial_uid"),
        "id": detail.get("primary_registry_id") or result.get("id"),
        "registry_ids": detail.get("registry_ids") or result.get("registry_ids", []),
        "title": title,
        "brief_summary": detail.get("brief_summary") or result.get("brief_summary", ""),
        "sponsor": detail.get("sponsor_summary") or result.get("sponsor", ""),
        "interventions": interventions or result.get("interventions", []),
        "overall_status": _status(detail.get("recruitment_status_normalized") or result.get("overall_status", "")),
        "phases": _phases(detail.get("phase_normalized") or result.get("phases")),
        "registration_date": detail.get("registration_date") or result.get("registration_date", ""),
        "countries": detail.get("countries") or result.get("countries", []),
        "last_update_date": detail.get("last_update_date") or result.get("last_update_date", ""),
        "sites": sites,
        "country_records": country_records,
        "patient_country_sites": patient_sites,
        "patient_country_site_count": len(patient_sites),
        "patient_country_location_records": patient_location_records,
        "patient_country_location_record_count": len(patient_location_records),
        "domestic_accessible": bool(patient_sites),
        "geography_class": geography_class,
        "parsed_criteria": detail.get("parsed_criteria") or result.get("parsed_criteria", {}),
        "eligibility_full": (detail.get("parsed_criteria") or {}).get("raw", result.get("eligibility_full", "")),
        "source_url": detail.get("source_url") or result.get("source_url", ""),
    })
    result["verification"] = {
        "status": "verified" if not mismatches else "verified_with_mismatch",
        "source": "WHO ICTRP MCP get_trial",
        "overall_status": result["overall_status"],
        "last_update_date": result["last_update_date"],
        "location_evidence": "named_site" if patient_sites else "country_only" if patient_location_records else "none",
        "mismatches": mismatches,
    }
    return result


def _merge_duplicate(existing: dict[str, Any], trial: dict[str, Any]) -> None:
    existing_ids = {
        str(item.get("registry_id") if isinstance(item, dict) else item).strip().upper()
        for item in existing.get("registry_ids") or []
    }
    for item in trial.get("registry_ids") or []:
        value = str(item.get("registry_id") if isinstance(item, dict) else item).strip().upper()
        if value and value not in existing_ids:
            existing.setdefault("registry_ids", []).append(item)
            existing_ids.add(value)
    for field in ("matched_by", "retrieval_provenance"):
        existing[field] = list(dict.fromkeys((existing.get(field) or []) + (trial.get(field) or [])))
    existing["matched_queries"] = (existing.get("matched_queries") or []) + (trial.get("matched_queries") or [])
    existing.setdefault("duplicate_registry_records", []).append({
        "trial_uid": trial.get("trial_uid"), "primary_registry_id": trial.get("id"), "source_url": trial.get("source_url"),
    })


def deduplicate_verified_trials(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge records connected by explicit registry IDs, including bridge records."""
    parents = list(range(len(trials)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    id_owner: dict[str, int] = {}
    for index, trial in enumerate(trials):
        for value in _ids(trial):
            if value in id_owner:
                union(index, id_owner[value])
            else:
                id_owner[value] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(trials)):
        groups.setdefault(find(index), []).append(index)
    deduped: list[dict[str, Any]] = []
    for indices in sorted(groups.values(), key=min):
        existing = trials[indices[0]]
        for index in indices[1:]:
            _merge_duplicate(existing, trials[index])
        deduped.append(existing)
    _annotate_possible_duplicates(deduped)
    return deduped


def _normalized_duplicate_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _annotate_possible_duplicates(trials: list[dict[str, Any]]) -> None:
    """Flag title/intervention lookalikes without merging independent protocols."""
    clusters: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for trial in trials:
        title = _normalized_duplicate_text(
            trial.get("scientific_title") or trial.get("title")
        )
        interventions = tuple(sorted(
            value for value in (
                _normalized_duplicate_text(item) for item in trial.get("interventions") or []
            ) if value
        ))
        if len(title) >= 40 and interventions:
            clusters.setdefault((title, interventions), []).append(trial)
    for cluster in clusters.values():
        if len(cluster) < 2:
            continue
        ids = [str(trial.get("id") or "") for trial in cluster]
        for trial in cluster:
            trial["possible_duplicate_records"] = [
                {
                    "trial_id": other.get("id"),
                    "primary_registry_id": other.get("primary_registry_id"),
                    "sponsor": other.get("sponsor"),
                    "reason": (
                        "Identical normalized scientific title and interventions; "
                        "kept separate because no authoritative registry-ID bridge exists."
                    ),
                }
                for other in cluster if other is not trial
            ]
            trial["possible_duplicate_cluster_ids"] = ids


def verify_batch(trials: list[dict[str, Any]], details: list[dict[str, Any]] | dict[str, Any], patient: dict[str, Any]) -> list[dict[str, Any]]:
    exact, aliases = detail_lookups(details)
    output = []
    for trial in trials:
        exact_ids = [trial.get("trial_uid"), trial.get("primary_registry_id"), trial.get("id")]
        detail = next((exact[str(value).strip().upper()] for value in exact_ids if value and str(value).strip().upper() in exact), None)
        if detail is None:
            detail = next((aliases[value] for value in _ids(trial) if value in aliases), None)
        output.append(verify_one(trial, detail, patient))
    return deduplicate_verified_trials(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input", required=True)
    parser.add_argument("--details", required=True)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8-sig"))
    data, details, patient = load(args.input), load(args.details), load(args.patient)
    if isinstance(data, dict):
        for bucket in ("included_trials", "match", "conditional", "exclude"):
            if bucket in data:
                data[bucket] = verify_batch(data[bucket], details, patient)
    else:
        data = verify_batch(data, details, patient)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
