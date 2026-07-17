"""Registry-specific presentation helpers with no clinical eligibility logic."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

PRODUCT_ALIASES = {
    "vegzelma": "Bevacizumab",
    "avastin": "Bevacizumab",
    "erbitux": "Cetuximab",
    "jnj-61186372": "Amivantamab",
}
GENERIC_INTERVENTIONS = {
    "product", "drug", "treatment", "none", "solution for infusion",
    "solution for injection", "placebo", "best supportive care", "n/a", "na",
    "not applicable", "not available", "standard of care", "soc therapy",
    "for", "clinical trial", "see study design above",
}
NON_THERAPEUTIC_TERMS = {
    "biopsy procedure", "biospecimen", "blood draw", "computed tomography", "ct scan",
    "diagnostic test", "echocardiography", "electrocardiogram", "imaging",
    "laboratory test", "magnetic resonance imaging", "mri", "muga",
    "multigated acquisition", "pharmacokinetic sampling", "pet scan",
    "digital photography", "questionnaire", "radiologic assessment", "sample collection",
    "specimen collection", "ultrasound", "bone scan", "cardiac monitoring",
    "electrocardiography", "molecular analysis", "pathology review",
    "physical examination", "screening test", "tumor assessment",
    "quality of life survey", "patient status engine", "wearable device",
    "ctdna test", "genomic tumor advisory board review", "oura ring",
    "withings", "daily weights", "patient monitoring device",
}
DOSING_SENTENCE_TERMS = {
    "will be supplied", "will be administered", "participants will receive",
    "subjects will receive", "dose escalation", "according to the dose",
    "is administered", "orally administered", "once daily", "twice daily", "apply to",
    "continuous administration", "accelerated escalation group", "study design above",
    "patients can be enrolled", "patient was enrolled", "once every",
    "on the premise of confirming", "will be maintained",
}
COUNTRY_ALIASES = {
    "中国": "china", "mainland china": "china", "pr china": "china",
    "usa": "united states", "us": "united states", "u.s.": "united states",
    "uk": "united kingdom", "u.k.": "united kingdom",
    "south korea": "republic of korea", "korea": "republic of korea",
}
NATIVE_REGISTRY_PREFIXES = {
    "china": ("CHICTR", "ITMCTR"),
    "india": ("CTRI/", "CTRI"),
    "japan": ("JPRN", "JRCT"),
    "netherlands": ("NL-", "NTR"),
    "australia": ("ACTRN",),
    "new zealand": ("ACTRN",),
    "germany": ("DRKS",),
    "iran": ("IRCT",),
    "republic of korea": ("KCT", "KCT000"),
    "brazil": ("RBR-",),
    "thailand": ("TCTR",),
    "sri lanka": ("SLCTR",),
}


def country_key(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    return COUNTRY_ALIASES.get(raw, raw)


def registry_ids(trial: dict[str, Any]) -> list[str]:
    values = [trial.get("id"), trial.get("primary_registry_id"), trial.get("trial_uid")]
    values.extend(
        item.get("registry_id") if isinstance(item, dict) else item
        for item in trial.get("registry_ids") or []
    )
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _clean_agent_name(value: str) -> str:
    name = re.sub(r"(?i)^(?:none|drug|experimental|intervention|biological|procedure|device|combination product)\s*:\s*", "", str(value or "")).strip()
    for _ in range(2):
        name = re.sub(r"(?i)^(?:(?:experimental|treatment|intervention|control)(?:\s+group)?|single drug research|combined administration|intervention\s*\d+)\s*:?\s*", "", name)
    name = re.sub(r"(?i)^biological\s+", "", name)
    name = re.sub(r"(?i)^combination of\s+", "", name)
    name = re.sub(r"(?i)^(?:low|medium|high)(?:est)?(?:[- ]dose)?\s+", "", name)
    name = re.sub(r"(?i)^(?:dose level|cohort|group|arm)\s*[A-Z0-9.-]*\s*:\s*", "", name)
    name = re.sub(r"(?i)^(.+?)\s*:\s*\d+(?:\.\d+)?(?:\s*x\s*10\^?\d+)?\s*(?:mg|mcg|g|ml|cells?)?\b.*$", r"\1", name)
    name = re.sub(r"(?i)^([A-Z]{2,}[-]?\d+)[- ](?:\d+(?:\.\d+)?\s*mg|recommended dose.*)$", r"\1", name)
    name = re.sub(
        r"(?i)(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:mg|mcg|ug|\u03bcg|g)"
        r"(?:\s*/\s*(?:kg|day|d|ml))?\s*",
        "",
        name,
    )
    name = re.sub(r"(?i)\s*\(\s*\d+(?:\.\d+)?\s*(?:mg|mcg|ug|\u03bcg|g)\b.*$", "", name)
    name = re.sub(r"(?i)\s*\(\s*(?:daily|orally|intravenous|for body weight)\b.*$", "", name)
    name = name.split(",", 1)[0].strip(" .:+")
    name = re.sub(r"(?i)\b([a-z][a-z0-9-]+)\s+\1\b", r"\1", name)
    name = re.sub(r"(?i)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)(?:/ml)?\b.*$", "", name).strip()
    name = re.sub(r"(?i)\s+(?:concentrate|solution|tablet|capsule|injection)\b.*$", "", name).strip()
    return PRODUCT_ALIASES.get(name.casefold(), name)


def _usable_agent_name(name: str) -> bool:
    folded = name.casefold()
    if not name or folded in GENERIC_INTERVENTIONS:
        return False
    if folded in {"autologous", "experimental", "experimental drug", "control", "control rx"}:
        return False
    if any(term in folded for term in NON_THERAPEUTIC_TERMS | DOSING_SENTENCE_TERMS):
        return False
    if re.fullmatch(r"(?i)[\d.\s/%-]*(?:mg|mcg|ug|\u03bcg|g|ml|q\d+w?)[\d.\s/%-]*", name):
        return False
    if len(name) > 80 or len(name.split()) > 10:
        return False
    if name.endswith((".", ";")) and len(name.split()) > 5:
        return False
    return True


def intervention_names(trial: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for item in trial.get("interventions") or []:
        raw = (item.get("intervention_name_raw") if isinstance(item, dict) else str(item)) or ""
        intervention_type = str(item.get("intervention_type") or item.get("type") or "") if isinstance(item, dict) else ""
        if intervention_type.casefold() in {"diagnostic test", "procedure"} and any(
            term in raw.casefold() for term in NON_THERAPEUTIC_TERMS
        ):
            continue
        if "product name:" in raw.casefold():
            values = re.findall(r"(?i)Product Name:\s*([^,]*)", raw)
        elif raw.casefold().startswith("hifu system "):
            values = []
        else:
            values = re.split(r"\s*\+\s*", raw)
        for value in values:
            name = _clean_agent_name(value)
            if _usable_agent_name(name):
                output.append(name)
    return list(dict.fromkeys(output))

def _clean_registry_title(value: Any) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip(" .")
    title = re.sub(
        r"(?i)^(?:a |an )?(?:phase\s+[0-4ivx?/ -]+\s+)?"
        r"(?:open-label\s+|multicenter\s+|randomized\s+|single-center\s+)*"
        r"(?:(?:clinical\s+)?(?:study|trial)\s+(?:of|to evaluate|evaluating)\s+|the study of )",
        "",
        title,
    ).strip(" .")
    title = re.sub(r"(?i)^(?:the )?(?:safety|efficacy)(?:,? safety)? and (?:efficacy|safety) of\s+", "", title)
    title = re.sub(r"(?i)^study on the (?:safety|efficacy|safety and efficacy|safety and tolerability) of\s+", "", title)
    return title


def patient_facing_title(trial: dict[str, Any], language: str) -> str:
    names = intervention_names(trial)
    public_title = _clean_registry_title(trial.get("title"))
    scientific_title = _clean_registry_title(trial.get("scientific_title"))
    raw_title = public_title or scientific_title

    if "amivantamab" in raw_title.casefold() and "folfiri" in raw_title.casefold():
        base = "Amivantamab + FOLFIRI vs Cetuximab/Bevacizumab + FOLFIRI"
    else:
        coded = [
            name for name in names
            if re.search(r"(?i)^(?:[A-Z]{2,8}-?\d|RMC-|JAB-|BGB-|D3S-)", name)
        ]
        ordered = coded + [name for name in names if name not in coded]
        base = " + ".join(ordered[:4])

    sentence_like = any(term in base.casefold() for term in DOSING_SENTENCE_TERMS)
    if len(base) > 120 or sentence_like:
        base = ""

    if not base:
        agent_source = f"{public_title} {scientific_title}"
        agents = re.findall(
            r"\b(?:[A-Z]{2,8}[- ]?\d{3,8}|[A-Za-z]{2,8}\d+(?:-[A-Za-z0-9]+)+|sotorasib|adagrasib|cetuximab|"
            r"bevacizumab|amivantamab|[a-z][a-z-]{3,}(?:mab|nib|parib|rasib|sertib))\b",
            agent_source,
            flags=re.I,
        )
        agents = list(dict.fromkeys(agent.strip() for agent in agents))
        base = " + ".join(agents[:4])

    if not base:
        base = scientific_title or public_title
    if not base:
        base = str(trial.get("id") or "Untitled trial")

    mechanism = trial.get("mechanism_category") or {}
    label = (
        mechanism.get("label_zh" if language == "zh-CN" else "label_en")
        or mechanism.get("label")
        or ("其他" if language == "zh-CN" else "Other")
    )
    max_base = max(80, 180 - len(label) - 3)
    if len(base) > max_base:
        shortened = base[:max_base].rsplit(" ", 1)[0].rstrip(" +,;/.-")
        shortened = re.sub(r"(?i)\s+(?:with|for|of|in|and|or|the|a|an|to)$", "", shortened).rstrip(" +,;/.-")
        base = shortened + "..."
    return f"{base or 'Untitled trial'} · {label}"

def assess_country_evidence(trial: dict[str, Any], patient: dict[str, Any]) -> dict[str, Any]:
    country = str(patient.get("country") or "").strip()
    key = country_key(country)
    if int(trial.get("patient_country_site_count") or 0) > 0:
        return {
            "class": "domestic_named", "decision": "confirmed_in_country", "confidence": "high",
            "basis": ["named_site"], "review_method": "structured_evidence",
        }
    prefixes = NATIVE_REGISTRY_PREFIXES.get(key, ())
    ids = registry_ids(trial)
    if prefixes and any(value.upper().startswith(tuple(prefix.upper() for prefix in prefixes)) for value in ids):
        return {
            "class": "domestic_registry", "decision": "country_native_registry", "confidence": "medium",
            "basis": ["registry_jurisdiction"], "review_method": "deterministic_registry_rule",
            "rationale": "Registration in the patient's national registry does not prove a named open centre.",
        }
    if int(trial.get("patient_country_location_record_count") or 0) > 0:
        return {
            "class": "country_unverified", "decision": "country_mentioned_but_site_unverified", "confidence": "low",
            "basis": ["registry_country_list_only"], "review_method": "structured_conservative_review",
            "rationale": "A country record does not establish a named open patient-accessible centre.",
        }
    return {
        "class": "overseas", "decision": "no_patient_country_evidence", "confidence": "medium",
        "basis": [], "review_method": "structured_evidence",
    }


def resolved_trial_url(trial: dict[str, Any]) -> str:
    trial_id = str(trial.get("id") or trial.get("primary_registry_id") or "").strip()
    upper = trial_id.upper()
    if upper.startswith(("CTIS", "CTRI/", "CTRI")):
        return "https://trialsearch.who.int/Trial2.aspx?TrialID=" + quote(trial_id, safe="")
    if upper.startswith("NCT"):
        return "https://clinicaltrials.gov/study/" + upper
    url = str(trial.get("source_url") or "").strip()
    if "chictr.org.cn" in url:
        return url.replace("http://", "https://").replace("showproj.aspx", "showproj.html")
    return url or ("https://trialsearch.who.int/Trial2.aspx?TrialID=" + quote(trial_id, safe=""))
