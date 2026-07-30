"""Ground model-written publication narratives to deterministic prefetch records."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def canonical_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((
        parsed.scheme.lower(), parsed.netloc.lower(),
        parsed.path.rstrip("/"), parsed.query, "",
    ))


def _identifiers(candidate: dict[str, Any]) -> set[str]:
    return {
        value for value in (
            str(candidate.get("pmid") or "").strip().lower(),
            str(candidate.get("pmcid") or "").strip().lower(),
            str(candidate.get("doi") or "").strip().lower(),
        ) if value
    }


def _candidate_for(
    evidence: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    requested_url = canonical_url(evidence.get("url"))
    if requested_url:
        for candidate in candidates:
            if canonical_url(candidate.get("url")) == requested_url:
                return candidate
    haystack = " ".join(
        str(evidence.get(key) or "") for key in ("citation", "url")
    ).lower()
    for candidate in candidates:
        if any(
            re.search(rf"(?<![a-z0-9]){re.escape(identifier)}(?![a-z0-9])", haystack)
            for identifier in _identifiers(candidate)
        ):
            return candidate
    return None


def _citation(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get(key) or "").strip()
        for key in ("title", "authors", "journal", "year")
    ]
    citation = ". ".join(part.rstrip(".") for part in parts if part)
    identifiers = [
        f"{label}: {candidate[key]}"
        for label, key in (("PMID", "pmid"), ("PMCID", "pmcid"), ("DOI", "doi"))
        if candidate.get(key)
    ]
    return f"{citation}. {'; '.join(identifiers)}".strip(". ")


def ground_development_evidence(
    efficacy: dict[str, Any], publication_prefetch: dict[str, Any]
) -> dict[str, int]:
    """Drop ungrounded publications and replace identity fields from source data."""
    candidates = [
        item for item in publication_prefetch.get("candidates") or []
        if isinstance(item, dict) and canonical_url(item.get("url"))
    ]
    grounded: list[dict[str, Any]] = []
    rejected = 0
    seen: set[str] = set()
    for evidence in efficacy.get("development_evidence") or []:
        if not isinstance(evidence, dict):
            rejected += 1
            continue
        candidate = _candidate_for(evidence, candidates)
        if not candidate:
            rejected += 1
            continue
        url = canonical_url(candidate.get("url"))
        if url in seen:
            continue
        seen.add(url)
        grounded.append({
            **evidence,
            "citation": _citation(candidate),
            "url": url,
            "source": candidate.get("source") or "Europe PMC",
            "source_identifiers": {
                key: candidate.get(key)
                for key in ("pmid", "pmcid", "doi")
                if candidate.get(key)
            },
        })
    efficacy["development_evidence"] = grounded
    efficacy["evidence_search"] = {
        "status": "found" if grounded else "no_relevant_publication",
        "queries": publication_prefetch.get("queries") or [],
        "searched_at": publication_prefetch.get("searched_at"),
        "source": publication_prefetch.get("source") or "Europe PMC REST API",
        "prefetch_status": publication_prefetch.get("status"),
        "candidate_count": len(candidates),
        "grounded_count": len(grounded),
        "rejected_model_evidence_count": rejected,
    }
    return {
        "candidate_count": len(candidates),
        "grounded_count": len(grounded),
        "rejected_count": rejected,
    }
