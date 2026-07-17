"""Conservative, cancer-agnostic deterministic eligibility hard rules."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

RULESET_VERSION = "generic-hard-rules-v1"
_SEX = {"female": "female", "f": "female", "woman": "female", "women": "female",
        "male": "male", "m": "male", "man": "male", "men": "male"}
_ALL_SEXES = {"all", "both", "any"}
_AGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(year|years|yr|yrs|month|months|mo|mos)\s*$", re.I)


def _first(mapping: Mapping[str, Any], *keys: str) -> tuple[Any, str | None]:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key], key
    return None, None


def _section(trial: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("structured_eligibility", "eligibility"):
        value = trial.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", value):
        return float(value)
    return None


def _age_months(value: Any) -> float | None:
    number, unit = _number(value), "years"
    if number is None and isinstance(value, str):
        match = _AGE_RE.fullmatch(value)
        if not match:
            return None
        number, unit = float(match.group(1)), match.group(2).casefold()
    if number is None or number < 0:
        return None
    return number if unit.startswith("mo") else number * 12


def _normalized_sex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return _SEX.get(normalized, "all" if normalized in _ALL_SEXES else None)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes"}:
            return True
        if normalized in {"false", "no"}:
            return False
    return None


def _trigger(rule_id: str, field: str, patient_value: Any, trial_value: Any, reason: str) -> dict[str, Any]:
    return {"rule_id": rule_id, "patient_field": field, "patient_value": patient_value,
            "trial_value": trial_value, "reason": reason}


def evaluate_generic_hard_rules(patient: Mapping[str, Any], trial: Mapping[str, Any]) -> dict[str, Any]:
    """Compare only explicit structured facts; ambiguous data passes to the gater."""
    if not isinstance(patient, Mapping) or not isinstance(trial, Mapping):
        raise TypeError("patient and trial must be mappings")
    eligibility = _section(trial)
    triggered: list[dict[str, Any]] = []

    patient_age, patient_age_key = _first(patient, "age_years", "age")
    age_months = _age_months(patient_age)
    minimum_age, _ = _first(eligibility, "minimum_age", "min_age")
    maximum_age, _ = _first(eligibility, "maximum_age", "max_age")
    if minimum_age is None:
        minimum_age, _ = _first(trial, "minimum_age", "min_age")
    if maximum_age is None:
        maximum_age, _ = _first(trial, "maximum_age", "max_age")
    if age_months is not None and _age_months(minimum_age) is not None and age_months < _age_months(minimum_age):
        triggered.append(_trigger("GHR-AGE-MIN", patient_age_key or "age", patient_age, minimum_age,
                                  "Patient age is explicitly below the trial minimum age."))
    if age_months is not None and _age_months(maximum_age) is not None and age_months > _age_months(maximum_age):
        triggered.append(_trigger("GHR-AGE-MAX", patient_age_key or "age", patient_age, maximum_age,
                                  "Patient age is explicitly above the trial maximum age."))

    patient_sex, patient_sex_key = _first(patient, "sex_at_birth", "sex")
    trial_sex, _ = _first(eligibility, "sex", "gender")
    if trial_sex is None:
        trial_sex, _ = _first(trial, "sex", "gender")
    patient_sex_norm, trial_sex_norm = _normalized_sex(patient_sex), _normalized_sex(trial_sex)
    if patient_sex_norm in {"female", "male"} and trial_sex_norm in {"female", "male"} and patient_sex_norm != trial_sex_norm:
        triggered.append(_trigger("GHR-SEX", patient_sex_key or "sex", patient_sex, trial_sex,
                                  "Patient sex at birth explicitly conflicts with trial eligibility."))

    patient_ecog, patient_ecog_key = _first(patient, "ecog", "ecog_performance_status")
    ecog = _number(patient_ecog)
    min_ecog, _ = _first(eligibility, "minimum_ecog", "min_ecog", "ecog_min")
    max_ecog, _ = _first(eligibility, "maximum_ecog", "max_ecog", "ecog_max")
    if ecog is not None and _number(min_ecog) is not None and ecog < _number(min_ecog):
        triggered.append(_trigger("GHR-ECOG-MIN", patient_ecog_key or "ecog", patient_ecog, min_ecog,
                                  "Patient ECOG is explicitly below the trial's structured range."))
    if ecog is not None and _number(max_ecog) is not None and ecog > _number(max_ecog):
        triggered.append(_trigger("GHR-ECOG-MAX", patient_ecog_key or "ecog", patient_ecog, max_ecog,
                                  "Patient ECOG is explicitly above the trial's structured range."))

    patient_lines, patient_lines_key = _first(patient, "treatment_lines_completed", "treatment_lines")
    lines = _number(patient_lines)
    min_lines, _ = _first(eligibility, "minimum_prior_lines", "min_prior_lines")
    max_lines, _ = _first(eligibility, "maximum_prior_lines", "max_prior_lines")
    if lines is not None and _number(min_lines) is not None and lines < _number(min_lines):
        triggered.append(_trigger("GHR-PRIOR-LINES-MIN", patient_lines_key or "treatment_lines", patient_lines,
                                  min_lines, "Completed treatment lines are explicitly below the structured trial minimum."))
    if lines is not None and _number(max_lines) is not None and lines > _number(max_lines):
        triggered.append(_trigger("GHR-PRIOR-LINES-MAX", patient_lines_key or "treatment_lines", patient_lines,
                                  max_lines, "Completed treatment lines are explicitly above the structured trial maximum."))

    pregnant, pregnant_key = _first(patient, "pregnant", "is_pregnant")
    allows_pregnancy, _ = _first(eligibility, "allows_pregnancy", "pregnancy_allowed")
    if _boolean(pregnant) is True and _boolean(allows_pregnancy) is False:
        triggered.append(_trigger("GHR-PREGNANCY", pregnant_key or "pregnant", pregnant, allows_pregnancy,
                                  "Patient pregnancy explicitly conflicts with the structured trial constraint."))

    hard_exclude = bool(triggered)
    return {"ruleset_version": RULESET_VERSION,
            "disposition": "hard_exclude" if hard_exclude else "pass_to_gater",
            "hard_exclude": hard_exclude, "pass_to_gater": not hard_exclude,
            "triggered_rules": triggered}


def apply_generic_hard_rules(patient: Mapping[str, Any], trials: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate and partition trials without mutating caller-owned records."""
    hard_excluded: list[dict[str, Any]] = []
    pass_to_gater: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for source in trials:
        if not isinstance(source, Mapping):
            raise TypeError("each trial must be a mapping")
        trial = deepcopy(dict(source))
        decision = evaluate_generic_hard_rules(patient, trial)
        trial["generic_hard_rules"] = decision
        audit.append({"trial_id": trial.get("trial_uid") or trial.get("id") or trial.get("primary_registry_id"), **decision})
        (hard_excluded if decision["hard_exclude"] else pass_to_gater).append(trial)
    return {"ruleset_version": RULESET_VERSION, "hard_exclude": hard_excluded,
            "pass_to_gater": pass_to_gater, "audit": audit}
