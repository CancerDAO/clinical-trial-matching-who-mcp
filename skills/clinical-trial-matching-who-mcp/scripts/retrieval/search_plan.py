"""Search-plan structure and eight-branch recall coverage contract."""
from __future__ import annotations

from typing import Any

REQUIRED_DIMENSIONS = (
    "disease_biomarker", "pan_tumor", "combination_targets", "pathway_resistance",
    "named_drug", "cell_therapy", "immune", "chinese_registry_terms",
)
DIMENSION_HINTS = {
    "disease_biomarker": ("疾病", "突变特异", "disease", "exact"),
    "pan_tumor": ("泛化", "泛实体瘤", "pan-tumor", "pan tumor", "all comers"),
    "combination_targets": ("联合靶点", "combination", "egfr/shp2", "egfr", "shp2"),
    "pathway_resistance": ("通路", "耐药", "pathway", "resistance", "pan-kras", "ras-on"),
    "named_drug": ("具体药物", "药物名", "named drug", "drug names"),
    "cell_therapy": ("细胞治疗", "cell therapy", "car-t", "tcr-t", "til"),
    "immune": ("免疫", "immune", "checkpoint", "pd-1"),
    "chinese_registry_terms": ("中文", "chictr", "中国注册"),
}


def _dimension(group: dict[str, Any]) -> str:
    explicit = str(group.get("dimension") or "").strip()
    if explicit in REQUIRED_DIMENSIONS:
        return explicit
    label = str(group.get("label") or "").casefold()
    for dimension, hints in DIMENSION_HINTS.items():
        if any(hint.casefold() in label for hint in hints):
            return dimension
    return ""


def search_plan_coverage(plan: dict[str, Any]) -> dict[str, Any]:
    present = list(dict.fromkeys(_dimension(group) for group in plan.get("keyword_groups") or [] if _dimension(group)))
    return {
        "required": list(REQUIRED_DIMENSIONS),
        "present": present,
        "missing": [dimension for dimension in REQUIRED_DIMENSIONS if dimension not in present],
        "unclassified_groups": [
            str(group.get("label") or "") for group in plan.get("keyword_groups") or [] if not _dimension(group)
        ],
    }


def validate_search_plan(plan: dict[str, Any], *, require_full_coverage: bool = True) -> list[str]:
    errors: list[str] = []
    groups = plan.get("keyword_groups") or []
    if not groups:
        return ["keyword_groups is required"]
    for index, group in enumerate(groups):
        if not group.get("label"):
            errors.append(f"keyword_groups[{index}].label is required")
        queries = group.get("queries") or []
        if not queries:
            errors.append(f"keyword_groups[{index}].queries is empty")
        for query_index, query in enumerate(queries):
            if not str(query.get("condition") or "").strip() and not str(query.get("term") or "").strip():
                errors.append(f"keyword_groups[{index}].queries[{query_index}] has no condition or term")
    if require_full_coverage:
        coverage = search_plan_coverage(plan)
        if coverage["missing"]:
            errors.append("missing required recall dimensions: " + ", ".join(coverage["missing"]))
    return errors


def generate_search_plan_prompt(patient_text: str) -> str:
    return f"""Create a strict JSON clinical-trial search plan for this oncology patient.
Preserve all eight original recall branches. Every keyword group must include a `dimension`
using exactly one of these values:
1. disease_biomarker — disease plus exact biomarker;
2. pan_tumor — pan-solid-tumor plus biomarker;
3. combination_targets — rational combinations such as EGFR/SHP2/SOS1;
4. pathway_resistance — pathway and resistance strategies;
5. named_drug — exhaustive approved and investigational drug names and aliases;
6. cell_therapy — cell and biologic therapies independent of the mutation;
7. immune — immune strategies appropriate to MSI/MSS and prior checkpoint exposure;
8. chinese_registry_terms — Chinese registry terms, including single-token alternatives.
Each group must contain a label and queries with condition and term. Include treatment_lines
and hard_exclude.first_line_only plus explicit molecular mismatch rules. Do not filter by country;
country is applied later for domestic/international reporting.

Patient:
{patient_text}

Return JSON only."""