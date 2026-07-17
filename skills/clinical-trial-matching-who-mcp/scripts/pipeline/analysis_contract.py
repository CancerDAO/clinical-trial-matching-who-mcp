"""Contracts between deterministic retrieval and model-executed clinical subskills."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "clinical-subskills-analysis-v1"
JOBS_SCHEMA_VERSION = "clinical-analysis-jobs-v2"
SUBSKILLS = (
    "trial-gater",
    "trial-risk-annotator",
    "trial-efficacy-contextualizer",
    "decision-synthesizer",
)
VERDICTS = {"match", "conditional", "exclude"}


def report_language(patient: dict[str, Any]) -> str:
    """Return the one report language used by jobs, validation and rendering."""
    configured = str(patient.get("report_language") or "").strip()
    if configured:
        return configured
    country = str(patient.get("country") or "").strip().casefold()
    return "zh-CN" if country in {"china", "\u4e2d\u56fd", "mainland china"} else "en"


ANALYSIS_TRIAL_FIELDS = (
    "id", "trial_uid", "primary_registry_id", "registry_ids", "title", "scientific_title",
    "brief_summary", "disease_text", "interventions", "intervention_summary", "phases",
    "overall_status", "sponsor", "eligibility_excerpt", "eligibility_full", "parsed_criteria",
    "matched_by", "matched_dimensions", "matched_queries", "mechanism_category", "feasibility",
    "country_assessment", "patient_country", "patient_country_site_count",
    "patient_country_location_record_count", "patient_country_sites", "database_as_of",
    "last_update_date", "resolved_source_url", "verification", "exclude_reason",
    "hard_excluded", "hard_exclusion",
)


def compact_trial_for_analysis(trial: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky registry payloads that do not inform the four model subskills."""
    compact = {key: trial[key] for key in ANALYSIS_TRIAL_FIELDS if key in trial}
    sites = list(compact.get("patient_country_sites") or [])
    if len(sites) > 10:
        compact["patient_country_sites"] = sites[:10]
        compact["patient_country_sites_truncated"] = True
    return compact

class AnalysisContractError(ValueError):
    pass


_MOJIBAKE_MARKERS = ("?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "\x80", "\x81", "\x82", "\x83", "\x84", "\x85")


def _cjk_count(value: str) -> int:
    return sum("\u3400" <= char <= "\u9fff" for char in value)


def _c1_control_count(value: str) -> int:
    return sum("\x80" <= char <= "\x9f" for char in value)


def repair_mojibake(value: Any) -> Any:
    """Repair strict UTF-8-as-Latin-1 corruption without touching normal text."""
    if isinstance(value, dict):
        return {key: repair_mojibake(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repair_mojibake(item) for item in value]
    if not isinstance(value, str) or not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    improved_cjk = _cjk_count(repaired) > _cjk_count(value) + 2
    removed_controls = _c1_control_count(value) > 0 and _c1_control_count(repaired) == 0
    return repaired if improved_cjk or removed_controls else value


def build_analysis_jobs(
    patient: dict[str, Any], trials: list[dict[str, Any]], skills_root: Path, *, batch_size: int = 5
) -> dict[str, Any]:
    """Build first-stage gater packets for every non-hard-excluded candidate."""
    skill_paths = {name: str((skills_root / name / "SKILL.md").resolve()) for name in SUBSKILLS}
    target_language = report_language(patient)
    missing = [name for name, path in skill_paths.items() if not Path(path).exists()]
    if missing:
        raise AnalysisContractError(f"Missing canonical subskills: {', '.join(missing)}")
    hard_excluded = [trial for trial in trials if _is_hard_excluded(trial)]
    gating_trials = [trial for trial in trials if not _is_hard_excluded(trial)]
    batches = []
    for start in range(0, len(gating_trials), max(1, batch_size)):
        batch = [compact_trial_for_analysis(trial) for trial in gating_trials[start:start + max(1, batch_size)]]
        batches.append({
            "batch_id": f"clinical-gater-{start // max(1, batch_size) + 1:03d}",
            "stage": "gater",
            "patient": patient,
            "trials": batch,
            "required_execution_order": ["trial-gater"],
            "output_schema": SCHEMA_VERSION,
            "target_language": target_language,
            "language_instruction": "Write all patient-facing eligibility narratives in target_language.",
        })
    return {
        "schema_version": JOBS_SCHEMA_VERSION,
        "workflow": "gater_then_deep_analysis",
        "stage": "gater",
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "skill_paths": skill_paths,
        "batch_size": batch_size,
        "trial_count": len(gating_trials),
        "input_trial_count": len(trials),
        "hard_excluded_trial_ids": [_trial_id(trial) for trial in hard_excluded],
        "batches": batches,
        "deep_stage": {
            "created_from_verdicts": ["match", "conditional"],
            "required_execution_order": ["trial-risk-annotator", "trial-efficacy-contextualizer"],
            "output_schema": SCHEMA_VERSION,
        },
        "decision_job": {
            "skill": "decision-synthesizer",
            "runs_after_all_batches": True,
            "input": "patient + analyzed_trials",
            "target_language": target_language,
        },
        "guardrail": "A formal report must not be generated until an LLM subskill analysis bundle passes validation.",
    }


def _trial_id(trial: dict[str, Any]) -> str:
    return str(trial.get("id") or trial.get("trial_id") or "").strip()


def _is_hard_excluded(trial: dict[str, Any]) -> bool:
    return bool(trial.get("hard_excluded") or trial.get("hard_exclusion") or trial.get("exclude_reason"))


def build_deep_analysis_jobs(
    patient: dict[str, Any], trials: list[dict[str, Any]], gating_results: list[dict[str, Any]],
    skills_root: Path, *, batch_size: int = 5,
) -> dict[str, Any]:
    """Build second-stage packets only for model-gated match/conditional trials."""
    skill_paths = {name: str((skills_root / name / "SKILL.md").resolve()) for name in SUBSKILLS}
    missing = [
        name for name in ("trial-risk-annotator", "trial-efficacy-contextualizer")
        if not Path(skill_paths[name]).exists()
    ]
    if missing:
        raise AnalysisContractError(f"Missing canonical subskills: {', '.join(missing)}")
    trial_by_id = {_trial_id(trial): trial for trial in trials if not _is_hard_excluded(trial)}
    gating_by_id: dict[str, dict[str, Any]] = {}
    for item in gating_results:
        trial_id = _trial_id(item)
        _require(trial_id in trial_by_id, f"Unexpected gater trial_id {trial_id}")
        _require(trial_id not in gating_by_id, f"Duplicate gater output for {trial_id}")
        _validate_gating(item)
        gating_by_id[trial_id] = item
    expected = set(trial_by_id)
    if set(gating_by_id) != expected:
        missing_ids = sorted(expected - set(gating_by_id))
        raise AnalysisContractError(f"Gater coverage mismatch; missing={missing_ids[:10]}")

    selected = [
        (trial_id, trial_by_id[trial_id], item["gating"])
        for trial_id, item in gating_by_id.items()
        if item["gating"]["verdict"] in {"match", "conditional"}
    ]
    size = max(1, batch_size)
    target_language = report_language(patient)
    batches = []
    for start in range(0, len(selected), size):
        rows = [
            {**compact_trial_for_analysis(trial), "gating": gating}
            for _, trial, gating in selected[start:start + size]
        ]
        batches.append({
            "batch_id": f"clinical-deep-{start // size + 1:03d}",
            "stage": "deep",
            "patient": patient,
            "trials": rows,
            "required_execution_order": ["trial-risk-annotator", "trial-efficacy-contextualizer"],
            "output_schema": SCHEMA_VERSION,
            "target_language": target_language,
            "language_instruction": "Write all patient-facing risk and efficacy narratives in target_language.",
            "evidence_instruction": "Search for agent-specific preclinical and prior clinical publications and emit development_evidence plus evidence_search. Never infer that a publication exists merely because a trial is recruiting.",
        })
    selected_ids = {trial_id for trial_id, _, _ in selected}
    return {
        "schema_version": JOBS_SCHEMA_VERSION,
        "workflow": "gater_then_deep_analysis",
        "stage": "deep",
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "skill_paths": skill_paths,
        "batch_size": batch_size,
        "trial_count": len(selected),
        "source_gater_trial_count": len(gating_results),
        "excluded_trial_ids": sorted(set(gating_by_id) - selected_ids),
        "batches": batches,
    }

def _require(value: Any, message: str) -> None:
    if not value:
        raise AnalysisContractError(message)


def _validate_gating(item: dict[str, Any]) -> None:
    gating = item.get("gating")
    _require(isinstance(gating, dict), f"{item.get('trial_id')}: missing trial-gater output")
    if gating.get("verdict") not in VERDICTS:
        raise AnalysisContractError(f"{item.get('trial_id')}: invalid gating verdict")
    confidence = gating.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise AnalysisContractError(f"{item.get('trial_id')}: gating confidence must be 0..1")
    for key in ("inclusion_evaluation", "exclusion_evaluation", "hard_rules_triggered", "blockers_satisfied", "blockers_failed", "blockers_pending"):
        if not isinstance(gating.get(key), list):
            raise AnalysisContractError(f"{item.get('trial_id')}: gating.{key} must be a list")
    _require(str(gating.get("rationale") or "").strip(), f"{item.get('trial_id')}: gating rationale is required")


_CANCER_ALIASES = {
    "crc": ("crc", "colorectal cancer", "colorectal carcinoma", "结直肠癌", "结肠癌", "直肠癌"),
    "nsclc": ("nsclc", "non-small cell lung cancer", "non small cell lung cancer", "非小细胞肺癌"),
    "sclc": ("sclc", "small cell lung cancer", "小细胞肺癌"),
    "hcc": ("hcc", "hepatocellular carcinoma", "肝细胞癌"),
    "rcc": ("rcc", "renal cell carcinoma", "肾细胞癌"),
    "pdac": ("pdac", "pancreatic ductal adenocarcinoma", "胰腺导管腺癌"),
    "tnbc": ("tnbc", "triple-negative breast cancer", "triple negative breast cancer", "三阴性乳腺癌"),
}


def _cancer_context_matches(cancer: str, context: str) -> bool:
    cancer_folded = cancer.strip().casefold()
    context_folded = context.strip().casefold()
    if not cancer_folded or cancer_folded in context_folded or context_folded in cancer_folded:
        return True
    terms = _CANCER_ALIASES.get(cancer_folded, (cancer_folded,))
    return any(term.casefold() in context_folded for term in terms)

def _validate_risk(item: dict[str, Any], patient: dict[str, Any]) -> None:
    risk = item.get("risk_annotation")
    _require(isinstance(risk, dict), f"{item.get('trial_id')}: missing risk subskill output")
    _require(isinstance(risk.get("risks"), list), f"{item.get('trial_id')}: risks must be a list")
    context = str(risk.get("patient_cancer_context") or "").casefold()
    cancer = str(patient.get("cancer_type") or "").casefold()
    if cancer and not _cancer_context_matches(cancer, context):
        raise AnalysisContractError(f"{item.get('trial_id')}: risk cancer context does not match patient")
    for entry in risk.get("risks") or []:
        _require(entry.get("applies_because"), f"{item.get('trial_id')}: risk applies_because is required")


def _validate_efficacy(item: dict[str, Any]) -> None:
    efficacy = item.get("efficacy_context")
    _require(isinstance(efficacy, dict), f"{item.get('trial_id')}: missing efficacy subskill output")
    snapshot = efficacy.get("efficacy_snapshot")
    _require(isinstance(snapshot, dict), f"{item.get('trial_id')}: missing efficacy_snapshot")
    _require(snapshot.get("match_type"), f"{item.get('trial_id')}: efficacy match_type is required")
    _require(snapshot.get("applies_because"), f"{item.get('trial_id')}: efficacy applies_because is required")
    if snapshot.get("match_type") != "no_data":
        source = snapshot.get("evidence_source")
        _require(isinstance(source, dict) and source.get("tier") and source.get("citation"), f"{item.get('trial_id')}: grounded evidence source is required")
    development = efficacy.get("development_evidence")
    search = efficacy.get("evidence_search")
    if (item.get("gating") or {}).get("verdict") != "exclude":
        _require(isinstance(development, list), f"{item.get('trial_id')}: development_evidence must be a list")
        _require(isinstance(search, dict), f"{item.get('trial_id')}: evidence_search is required")
        if search.get("status") not in {"found", "no_relevant_publication"}:
            raise AnalysisContractError(
                f"{item.get('trial_id')}: evidence_search.status must be found or no_relevant_publication"
            )
        _require(search.get("searched_at"), f"{item.get('trial_id')}: evidence_search.searched_at is required")
        _require(isinstance(search.get("queries"), list), f"{item.get('trial_id')}: evidence_search.queries must be a list")
        if search.get("status") == "found":
            _require(development, f"{item.get('trial_id')}: found evidence requires development_evidence")
        for evidence in development:
            _require(isinstance(evidence, dict), f"{item.get('trial_id')}: invalid development evidence")
            for key in ("evidence_stage", "citation", "url", "findings", "applicability", "limitations"):
                _require(evidence.get(key), f"{item.get('trial_id')}: development evidence {key} is required")
    vs_soc = efficacy.get("vs_soc")
    _require(isinstance(vs_soc, dict), f"{item.get('trial_id')}: vs_soc is required")
    if vs_soc.get("available"):
        _require(vs_soc.get("head_to_head_summary"), f"{item.get('trial_id')}: vs_soc summary is required")


def validate_analysis_bundle(
    bundle: dict[str, Any], patient: dict[str, Any], expected_trial_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Reject heuristic/example outputs and validate all original subskill contracts."""
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise AnalysisContractError(f"Expected analysis schema {SCHEMA_VERSION}")
    provenance = bundle.get("analysis_provenance") or {}
    if provenance.get("mode") != "llm_subskills":
        raise AnalysisContractError("Formal analysis must use mode=llm_subskills")
    _require(provenance.get("model"), "analysis_provenance.model is required")
    _require(provenance.get("completed_at"), "analysis_provenance.completed_at is required")
    expected_language = report_language(patient)
    if provenance.get("output_language") != expected_language:
        raise AnalysisContractError(f"analysis output_language must be {expected_language}")
    analyzed = bundle.get("analyzed_trials")
    if not isinstance(analyzed, list):
        raise AnalysisContractError("analyzed_trials must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for item in analyzed:
        trial_id = str(item.get("trial_id") or "").strip()
        _require(trial_id, "Every analysis item requires trial_id")
        if trial_id in by_id:
            raise AnalysisContractError(f"Duplicate analysis for {trial_id}")
        _validate_gating(item)
        if item["gating"]["verdict"] in {"match", "conditional"}:
            _validate_risk(item, patient)
            _validate_efficacy(item)
        by_id[trial_id] = item
    expected = set(expected_trial_ids)
    actual = set(by_id)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AnalysisContractError(f"Analysis coverage mismatch; missing={missing[:10]} extra={extra[:10]}")
    decision = bundle.get("decision_report")
    _require(isinstance(decision, dict), "decision-synthesizer output is required")
    _require(isinstance(decision.get("decision_paths"), list), "decision_report.decision_paths must be a list")
    _require(isinstance(decision.get("goals_of_care"), dict), "decision_report.goals_of_care is required")
    return by_id


def normalized_report_analysis(item: dict[str, Any]) -> dict[str, Any]:
    """Map original subskill outputs to the report contract and repair safe encoding corruption."""
    item = repair_mojibake(item)
    gating = item["gating"]
    risk = item.get("risk_annotation") or {"risks": []}
    efficacy = item.get("efficacy_context") or {}
    snapshot = efficacy.get("efficacy_snapshot") or {}
    development = efficacy.get("development_evidence")
    search = efficacy.get("evidence_search")
    if (item.get("gating") or {}).get("verdict") != "exclude":
        _require(isinstance(development, list), f"{item.get('trial_id')}: development_evidence must be a list")
        _require(isinstance(search, dict), f"{item.get('trial_id')}: evidence_search is required")
        if search.get("status") not in {"found", "no_relevant_publication"}:
            raise AnalysisContractError(
                f"{item.get('trial_id')}: evidence_search.status must be found or no_relevant_publication"
            )
        _require(search.get("searched_at"), f"{item.get('trial_id')}: evidence_search.searched_at is required")
        _require(isinstance(search.get("queries"), list), f"{item.get('trial_id')}: evidence_search.queries must be a list")
        if search.get("status") == "found":
            _require(development, f"{item.get('trial_id')}: found evidence requires development_evidence")
        for evidence in development:
            _require(isinstance(evidence, dict), f"{item.get('trial_id')}: invalid development evidence")
            for key in ("evidence_stage", "citation", "url", "findings", "applicability", "limitations"):
                _require(evidence.get(key), f"{item.get('trial_id')}: development evidence {key} is required")
    vs_soc = efficacy.get("vs_soc") or {}
    summary = vs_soc.get("head_to_head_summary") or snapshot.get("applies_because") or ""
    risks = []
    for entry in risk.get("risks") or []:
        narrative = entry.get("narrative") or []
        risks.append({
            "mechanism": entry.get("mechanism") or entry.get("key") or "Trial-specific risk",
            "risk_level": entry.get("risk_level") or "uncertain",
            "notes": narrative if isinstance(narrative, list) else [str(narrative)],
            "applies_because": entry.get("applies_because"),
        })
    return {
        "trial_id": item["trial_id"],
        "gating": {
            "verdict": gating["verdict"],
            "confidence": gating["confidence"],
            "satisfied": gating.get("blockers_satisfied") or [],
            "pending": (gating.get("blockers_pending") or []) + (gating.get("advisors_unknown") or []),
            "exclusion_reasons": gating.get("blockers_failed") or [],
            "rationale": gating.get("rationale") or "",
            "hard_rules_triggered": gating.get("hard_rules_triggered") or [],
            "inclusion_evaluation": gating.get("inclusion_evaluation") or [],
            "exclusion_evaluation": gating.get("exclusion_evaluation") or [],
        },
        "risks": risks,
        "efficacy_context": {
            "summary": summary,
            "snapshot": snapshot,
            "vs_soc": vs_soc,
            "development_evidence": efficacy.get("development_evidence") or [],
            "evidence_search": efficacy.get("evidence_search") or {},
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))
