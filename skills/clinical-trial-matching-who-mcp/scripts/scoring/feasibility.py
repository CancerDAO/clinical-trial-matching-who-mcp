"""Patient-relative five-dimension feasibility scoring.

Mechanism relevance and eligibility verdict are intentionally scored elsewhere.
This module only estimates operational feasibility for the patient's location.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, field
from typing import Any

WEIGHTS = {
    "recruiting_status": 0.55,
    "geographic_access": 0.00,
    "time_cost": 0.20,
    "financial_cost": 0.00,
    "slot_availability": 0.25,
}
AFFORDABILITY_TIERS = {
    "low": {"domestic": 1.0, "domestic_travel": 0.8, "international": 0.05},
    "medium": {"domestic": 1.0, "domestic_travel": 1.0, "international": 0.4},
    "high": {"domestic": 1.0, "domestic_travel": 1.0, "international": 0.85},
}


@dataclass
class FeasibilityScore:
    composite: float = 0.0
    sub_scores: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    promote_to_decision_report: bool = True


def _country_key(value: Any) -> str:
    aliases = {"中国": "china", "mainland china": "china", "usa": "united states", "us": "united states", "uk": "united kingdom"}
    raw = str(value or "").strip().casefold()
    return aliases.get(raw, raw)


def patient_country_sites(trial: dict, patient: dict) -> list[dict]:
    if "patient_country_sites" in trial:
        return list(trial.get("patient_country_sites") or [])
    country = _country_key(patient.get("country"))
    if not country:
        return []
    sites = trial.get("sites") or []
    matches = [site for site in sites if _country_key(site.get("country")) == country]
    return matches


def patient_country_site_count(trial: dict, patient: dict) -> int:
    if "patient_country_site_count" in trial:
        return int(trial.get("patient_country_site_count") or 0)
    return len(patient_country_sites(trial, patient))

def patient_country_location_record_count(trial: dict, patient: dict) -> int:
    if "patient_country_location_record_count" in trial:
        return int(trial.get("patient_country_location_record_count") or 0)
    country = _country_key(patient.get("country"))
    return sum(1 for site in trial.get("sites") or [] if _country_key(site.get("country")) == country)


def _months_old(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        return (now - parsed.astimezone(dt.timezone.utc)).days / 30.0
    except (TypeError, ValueError):
        return None


def score_recruiting_status(trial: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    status = str(trial.get("overall_status") or trial.get("verification", {}).get("overall_status", "")).upper()
    status = status.replace(" ", "_").replace(",", "")
    if status == "RECRUITING":
        base = 1.0
    elif status == "ACTIVE_NOT_RECRUITING":
        base = 0.3
        flags.append("Trial is active but not recruiting")
    elif status in {"NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}:
        base = 0.5
        flags.append(f"Enrollment status is {status}")
    else:
        base = 0.1
        flags.append(f"Trial status is not recruiting ({status or 'unknown'})")
    age = _months_old(trial.get("last_update_date") or trial.get("verification", {}).get("last_update_date", ""))
    if age is not None and age > 18:
        base *= 0.5
        flags.append(f"Registry record last updated {age:.0f} months ago")
    elif age is not None and age > 12:
        base *= 0.7
        flags.append(f"Registry record last updated {age:.0f} months ago")
    return min(1.0, max(0.0, base)), flags


def score_geographic_access(trial: dict, patient: dict) -> tuple[float, list[str]]:
    count = patient_country_site_count(trial, patient)
    country = patient.get("country")
    if not country:
        return 0.5, ["Patient country is missing; geographic access cannot be classified"]
    willing_international = bool(patient.get("willing_to_travel_internationally", False))
    if count >= 10:
        return 1.0, []
    if count >= 3:
        return 0.85, []
    if count >= 1:
        return 0.7, [f"Only {count} named site(s) in {country}; slot access may be limited"]
    if patient_country_location_record_count(trial, patient) > 0:
        return 0.55, [f"{country} is listed, but no named domestic site is available; access requires verification"]
    if willing_international:
        return 0.5, [f"No site in {country}; international travel is required"]
    return 0.15, [f"No site in {country}; patient is not willing to travel internationally"]


def _intervention_text(trial: dict) -> str:
    values = trial.get("interventions") or []
    return " ".join(str(item) for item in values).casefold() + " " + str(trial.get("title", "")).casefold()


def score_time_cost(trial: dict, patient: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    text = _intervention_text(trial)
    cell = any(term in text for term in ("car-t", "tcr-t", "tcr t", "til therapy", "cell therapy"))
    cell = cell or bool(re.search(r"\bcar[\s-]+t\b", text))
    base = 0.9
    if cell:
        base = 0.5
        flags.append("Cell therapy may require a 4-8 week manufacturing window")
    if patient.get("treatment_lines_completed", 0) >= 1:
        base *= 0.95
        flags.append("Recent systemic therapy may require washout")
    return min(1.0, max(0.0, base)), flags


def score_financial_cost(trial: dict, patient: dict) -> tuple[float, list[str]]:
    tier = patient.get("affordability_tier", "medium")
    if not patient.get("country"):
        return 0.5, ["Patient country is missing; travel cost cannot be classified"]
    weights = AFFORDABILITY_TIERS.get(tier, AFFORDABILITY_TIERS["medium"])
    sites = patient_country_sites(trial, patient)
    city = str(patient.get("city") or patient.get("patient_location") or "").casefold()
    site_cities = [str(site.get("city") or "").strip().casefold() for site in sites]
    same_city = any(site_city and (site_city in city or city in site_city) for site_city in site_cities)
    if not sites and patient_country_location_record_count(trial, patient) > 0:
        return min(weights["domestic_travel"], 0.65), [f"{patient.get('country')} is listed, but the domestic center is not identified"]
    if not sites:
        return weights["international"], [f"International trial; affordability_tier={tier}"]
    if same_city:
        return weights["domestic"], []
    return weights["domestic_travel"], ["Domestic cross-city travel is likely"]


def score_slot_availability(trial: dict, patient: dict | None = None) -> tuple[float, list[str]]:
    flags: list[str] = []
    age = _months_old(trial.get("last_update_date") or trial.get("verification", {}).get("last_update_date", ""))
    if age is None:
        base = 0.6
        flags.append("Slot availability is unknown")
    elif age < 3:
        base = 0.85
    elif age < 6:
        base = 0.7
    elif age < 12:
        base = 0.55
    else:
        base = 0.4
        flags.append(f"Updated {age:.0f} months ago; slot availability is uncertain")
    if patient and patient_country_site_count(trial, patient) >= 10:
        base = min(1.0, base + 0.1)
    return base, flags


def compute_feasibility(trial: dict, patient: dict) -> FeasibilityScore:
    fs = FeasibilityScore()
    scores_and_flags = [
        score_recruiting_status(trial), score_geographic_access(trial, patient),
        score_time_cost(trial, patient), score_financial_cost(trial, patient),
        score_slot_availability(trial, patient),
    ]
    fs.sub_scores = {key: round(value[0], 3) for key, value in zip(WEIGHTS, scores_and_flags)}
    fs.flags = [flag for _, flags in scores_and_flags for flag in flags]
    fs.composite = round(sum(WEIGHTS[key] * value for key, value in fs.sub_scores.items()), 3)
    scored_dimensions = (key for key, weight in WEIGHTS.items() if weight > 0)
    if any(fs.sub_scores[key] < 0.30 for key in scored_dimensions):
        fs.promote_to_decision_report = False
        fs.flags.append("Demoted from Top N because at least one feasibility dimension is below 0.30")
    return fs


def score_all(trials: list[dict], patient: dict) -> list[dict]:
    for trial in trials:
        if "error" not in trial:
            trial["feasibility"] = asdict(compute_feasibility(trial, patient))
    return trials


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input", required=True)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    patient = json.loads(Path(args.patient).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for bucket in ("included_trials", "match", "conditional", "exclude"):
            if bucket in data:
                data[bucket] = score_all(data[bucket], patient)
    else:
        data = score_all(data, patient)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
