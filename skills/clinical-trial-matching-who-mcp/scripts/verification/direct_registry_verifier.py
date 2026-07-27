"""Live recruitment verification against direct registry URLs before eligibility gating."""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable

ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}
INACTIVE = {
    "ACTIVE_NOT_RECRUITING", "COMPLETED", "TERMINATED", "WITHDRAWN",
    "SUSPENDED", "NO_LONGER_RECRUITING",
}
CTGOV = "https://clinicaltrials.gov/api/v2/studies"


def _status(value: Any) -> str:
    normalized = re.sub(r"[^A-Z]+", "_", str(value or "").upper()).strip("_")
    aliases = {
        "ACTIVE_NOT_RECRUITING": "ACTIVE_NOT_RECRUITING",
        "NOT_YET_RECRUITING": "NOT_YET_RECRUITING",
        "ENROLLING_BY_INVITATION": "ENROLLING_BY_INVITATION",
        "NOT_RECRUITING": "NO_LONGER_RECRUITING",
    }
    return aliases.get(normalized, normalized)


def _fetch(url: str, timeout: float) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "CancerDAO-live-registry-verifier/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.geturl(), response.read().decode("utf-8", errors="replace")


def _nct_id(trial: dict[str, Any]) -> str:
    values = [trial.get("id"), trial.get("primary_registry_id")]
    values.extend(
        item.get("registry_id") if isinstance(item, dict) else item
        for item in trial.get("registry_ids") or []
    )
    return next((str(value).upper() for value in values if re.fullmatch(r"NCT\d{8}", str(value or ""), re.I)), "")


def verify_one(
    trial: dict[str, Any], *, timeout: float = 20,
    fetcher: Callable[[str, float], tuple[str, str]] = _fetch,
) -> dict[str, Any]:
    checked_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    nct = _nct_id(trial)
    direct_url = f"{CTGOV}/{nct}" if nct else str(trial.get("source_url") or trial.get("resolved_source_url") or "")
    if not direct_url:
        return {"status": "unavailable", "checked_at": checked_at, "reason": "No direct registry URL"}
    try:
        resolved_url, body = fetcher(direct_url, timeout)
        if nct:
            payload = json.loads(body)
            module = (payload.get("protocolSection") or {}).get("statusModule") or {}
            live_status = _status(module.get("overallStatus"))
            updated = (module.get("lastUpdatePostDateStruct") or {}).get("date", "")
            source_url = f"https://clinicaltrials.gov/study/{nct}"
            method = "clinicaltrials.gov_v2_api"
        else:
            plain = " ".join(re.sub(r"<[^>]+>", " ", body).split())
            label = re.search(
                r"(?:recruitment|recruiting|trial|overall)\s+status\s*[:\-]?\s*(.{0,100})",
                plain, re.I,
            )
            status_window = label.group(1) if label else ""
            known = sorted(ACTIVE | INACTIVE, key=len, reverse=True)
            normalized_window = _status(status_window)
            live_status = next(
                (candidate for candidate in known
                 if candidate in normalized_window),
                "",
            )
            updated = ""
            source_url, method = resolved_url, "direct_registry_webpage"
        if live_status in ACTIVE:
            result_status = "active"
        elif live_status in INACTIVE:
            result_status = "inactive"
        else:
            result_status = "unknown"
        return {
            "status": result_status,
            "overall_status": live_status,
            "last_update_date": updated,
            "source_url": source_url,
            "method": method,
            "checked_at": checked_at,
            "http_reachable": True,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "error", "checked_at": checked_at, "source_url": direct_url,
            "http_reachable": False, "error": str(exc),
        }


def verify_and_partition(
    trials: list[dict[str, Any]], *, workers: int = 8, timeout: float = 20,
    verifier: Callable[..., dict[str, Any]] = verify_one,
) -> dict[str, Any]:
    copies = [deepcopy(trial) for trial in trials]
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 32))) as pool:
        results = list(pool.map(lambda trial: verifier(trial, timeout=timeout), copies))
    active_or_unknown: list[dict[str, Any]] = []
    inactive: list[dict[str, Any]] = []
    for trial, result in zip(copies, results):
        trial["live_registry_verification"] = result
        if result.get("overall_status"):
            trial["overall_status"] = result["overall_status"]
        (inactive if result.get("status") == "inactive" else active_or_unknown).append(trial)
    return {
        "active_or_unknown": active_or_unknown,
        "inactive": inactive,
        "audit": {
            "attempted": len(copies),
            "active": sum(result.get("status") == "active" for result in results),
            "inactive": len(inactive),
            "unknown": sum(result.get("status") == "unknown" for result in results),
            "errors": sum(result.get("status") in {"error", "unavailable"} for result in results),
            "reachable": sum(result.get("status") not in {"error", "unavailable"} for result in results),
            "complete": len(results) == len(copies),
            "policy": "Only an explicit non-enrolling status from a direct registry is excluded.",
        },
    }
