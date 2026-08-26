"""Deterministically correct high-impact drug facts in model narratives."""
from __future__ import annotations

import copy
import re
from typing import Any


RMC_6236 = re.compile(r"\bRMC[- ]6236\b", re.IGNORECASE)
IMMUNE_WORD = re.compile(r"\bimmunotherap(?:y|ies)\b", re.IGNORECASE)
RESOLVABLE_BLOCKER_MARKERS = (
    "washout", "wash-out", "requires discontinuation", "after discontinuation",
    "stop current", "current therapy active", "recent systemic therapy",
)


def is_resolvable_blocker(value: Any) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in RESOLVABLE_BLOCKER_MARKERS)


def partition_resolvable_blockers(
    failures: list[Any], *, verdict: str,
) -> tuple[list[Any], list[Any]]:
    if verdict != "conditional":
        return list(failures), []
    hard, pending = [], []
    for failure in failures:
        (pending if is_resolvable_blocker(failure) else hard).append(failure)
    return hard, pending


def _rmc_6236_false_immune_claim(value: Any) -> bool:
    text = str(value or "")
    return bool(RMC_6236.search(text) and IMMUNE_WORD.search(text))


def _correct_text(value: str) -> str:
    if not _rmc_6236_false_immune_claim(value):
        return value
    replacements = (
        (r"prior immunotherapy\s*\(RMC[- ]6236 ongoing\)",
         "current investigational RAS-targeted therapy (RMC-6236)"),
        (r"current immunotherapy treatment\s*[—-]\s*RMC[- ]6236 ongoing",
         "current investigational RAS-targeted therapy (RMC-6236)"),
        (r"active immunotherapy\s*\(RMC[- ]6236\)",
         "active investigational RAS-targeted therapy (RMC-6236)"),
        (r"RMC[- ]6236\s*\(pan-RAS/immunotherapy agent\)",
         "RMC-6236 (pan-RAS/RAS(ON) inhibitor)"),
        (r"RMC[- ]6236,?\s+an investigational immunotherapy",
         "RMC-6236, an investigational pan-RAS/RAS(ON) inhibitor"),
        (r"RMC[- ]6236 immunotherapy", "RMC-6236 targeted therapy"),
        (r"RMC[- ]6236 is classified as immunotherapy in this trial's exclusion context\.?",
         "RMC-6236 is not immunotherapy; protocol-specific investigational-drug washout must be confirmed."),
        (r"Although RMC[- ]6236 is not a classic checkpoint inhibitor, its immunomodulatory properties and ongoing experimental therapy constitute prior immunotherapy exposure\.?",
         "RMC-6236 is a pan-RAS/RAS(ON) inhibitor and does not constitute prior immunotherapy exposure."),
        (r"violating ['\"]no previous immunotherapy['\"] exclusion",
         "requiring protocol-specific investigational-drug washout confirmation"),
    )
    corrected = value
    for pattern, replacement in replacements:
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
    if (
        _rmc_6236_false_immune_claim(corrected)
        and "not immunotherapy" not in corrected.casefold()
        and "does not constitute prior immunotherapy" not in corrected.casefold()
    ):
        corrected += (
            " RMC-6236 is a pan-RAS/RAS(ON) inhibitor, not immunotherapy; "
            "only protocol-specific investigational-drug washout should be assessed."
        )
    return corrected


def _correct_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _correct_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_correct_value(item) for item in value]
    if isinstance(value, str):
        return _correct_text(value)
    return value


def _uln_conflicts(evaluations: list[Any]) -> list[str]:
    conflicts: list[str] = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        criterion = str(evaluation.get("criterion") or "")
        evidence = str(evaluation.get("evidence") or "")
        for analyte in ("ALT", "AST"):
            if analyte.casefold() not in criterion.casefold():
                continue
            actuals = [
                float(value) for value in re.findall(
                    rf"\b{analyte}\b[^.;]{{0,40}}?(\d+(?:\.\d+)?)\s*[×x]\s*ULN",
                    evidence, flags=re.IGNORECASE,
                )
            ]
            limits = [
                float(value) for value in re.findall(
                    r"[≤<]\s*(\d+(?:\.\d+)?)\s*[×x]\s*ULN",
                    criterion, flags=re.IGNORECASE,
                )
            ]
            if actuals and limits and max(actuals) > max(limits):
                actual, limit = max(actuals), max(limits)
                evaluation["verdict"] = "❌ 不符合"
                evaluation["evidence"] = re.sub(
                    rf"within\s+[≤<]\s*{limit:g}\s*[×x]\s*ULN",
                    f"exceeds the ≤{limit:g}×ULN limit",
                    evidence, flags=re.IGNORECASE,
                )
                note = (
                    f"{analyte} {actual:g}×ULN exceeds the stated ≤{limit:g}×ULN "
                    "screening threshold; repeat protocol-timed laboratory testing."
                )
                conflicts.append(note)
    return conflicts


def correct_analysis_clinical_facts(
    item: dict[str, Any], *, allow_verdict_change: bool = False,
) -> dict[str, Any]:
    """Correct known false drug-class claims and their gating consequences."""
    result = _correct_value(copy.deepcopy(item))
    original_gating = (item.get("gating") or {}) if isinstance(item, dict) else {}
    gating = result.get("gating") or {}
    original_failed = original_gating.get("blockers_failed") or []
    moved_indexes = {
        index for index, blocker in enumerate(original_failed)
        if _rmc_6236_false_immune_claim(blocker)
    }
    if moved_indexes:
        corrected_failed = gating.get("blockers_failed") or []
        moved = [
            corrected_failed[index] for index in sorted(moved_indexes)
            if index < len(corrected_failed)
        ]
        gating["blockers_failed"] = [
            blocker for index, blocker in enumerate(corrected_failed)
            if index not in moved_indexes
        ]
        pending = list(gating.get("blockers_pending") or [])
        for blocker in moved:
            note = (
                f"{blocker}; confirm protocol-specific washout. "
                "RMC-6236 is not immunotherapy."
            )
            if note not in pending:
                pending.append(note)
        gating["blockers_pending"] = pending
        if "R1" in (gating.get("hard_rules_triggered") or []):
            gating["hard_rules_triggered"] = [
                rule for rule in gating["hard_rules_triggered"] if rule != "R1"
            ]
        if (
            allow_verdict_change
            and gating.get("verdict") == "exclude"
            and not gating["blockers_failed"]
        ):
            gating["verdict"] = "conditional"
    for key in ("inclusion_evaluation", "exclusion_evaluation"):
        evaluations = gating.get(key) or []
        original_evaluations = original_gating.get(key) or []
        for index, evaluation in enumerate(evaluations):
            if not isinstance(evaluation, dict) or index >= len(original_evaluations):
                continue
            original = original_evaluations[index]
            criterion = str(original.get("criterion") or "")
            evidence = str(original.get("evidence") or "")
            if not _rmc_6236_false_immune_claim(evidence):
                continue
            if (
                "no previous immunotherapy" in criterion.casefold()
                or "prior immunotherapy" in criterion.casefold()
            ):
                evaluation["verdict"] = "✅ 无冲突"
                evaluation["evidence"] = (
                    "RMC-6236 is a pan-RAS/RAS(ON) inhibitor, not immunotherapy; "
                    "no separate prior immunotherapy is documented."
                )
            else:
                evaluation["verdict"] = "⚠️ 边界"
                evaluation["evidence"] = (
                    "RMC-6236 is a pan-RAS/RAS(ON) inhibitor, not immunotherapy. "
                    "Confirm the protocol-specific washout for an investigational targeted agent."
                )
    threshold_conflicts = _uln_conflicts(
        list(gating.get("inclusion_evaluation") or [])
        + list(gating.get("exclusion_evaluation") or [])
    )
    if threshold_conflicts:
        satisfied = list(gating.get("blockers_satisfied") or [])
        moved = [
            item for item in satisfied
            if "adequate organ function" in str(item).casefold()
            or "adequate hepatic" in str(item).casefold()
        ]
        gating["blockers_satisfied"] = [
            item for item in satisfied if item not in moved
        ]
        pending = list(gating.get("blockers_pending") or [])
        for note in threshold_conflicts:
            if note not in pending:
                pending.insert(0, note)
        gating["blockers_pending"] = pending
    result["gating"] = gating
    return result
