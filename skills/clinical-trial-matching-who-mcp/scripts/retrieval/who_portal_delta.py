"""Create an auditable WHO ICTRP registration-date delta from the public portal."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import http.cookiejar
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from disease_concepts import contains_cjk

PORTAL = "https://trialsearch.who.int"
ADVANCED = f"{PORTAL}/AdvSearch.aspx"
USER_AGENT = "CancerDAO-clinical-trial-matching/3.3 (research use)"


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}
        self.trial_ids: list[str] = []
        self.spans: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self._capture_id = ""
        self._capture_href = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("type", "").casefold() == "hidden" and values.get("name"):
            self.hidden[values["name"]] = values.get("value") or ""
        element_id = values.get("id") or ""
        if tag == "span" and element_id:
            self._capture_id, self._parts = element_id, []
        elif tag == "a" and element_id:
            self._capture_id, self._capture_href, self._parts = (
                element_id, values.get("href") or "", []
            )
        href = values.get("href") or ""
        match = re.search(r"Trial2\.aspx\?TrialID=([^&#]+)", href, re.I)
        if match:
            self.trial_ids.append(urllib.parse.unquote(match.group(1)))

    def handle_data(self, data: str) -> None:
        if self._capture_id:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_id and tag in {"span", "a"}:
            text = " ".join(" ".join(self._parts).split())
            self.spans[self._capture_id] = html.unescape(text)
            if self._capture_href:
                self.links[self._capture_id] = html.unescape(self._capture_href)
            self._capture_id, self._capture_href, self._parts = "", "", []


class WhoPortalClient:
    def __init__(self, *, timeout: float = 60, delay: float = 0.5) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.timeout = timeout
        self.delay = delay
        self._form: dict[str, str] | None = None

    def _open(self, url: str, data: bytes | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            request = urllib.request.Request(
                url, data=data, headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        raise RuntimeError(f"WHO portal request failed after 3 attempts: {last_error}")

    def search(
        self, *, title: str = "", condition: str = "", intervention: str = "",
        date_start: str, date_end: str,
    ) -> tuple[list[str], int]:
        if self._form is None:
            parser = _FormParser()
            parser.feed(self._open(ADVANCED))
            self._form = parser.hidden
        form = dict(self._form)
        form.update({
            "ctl00$ContentPlaceHolder1$txtTitle": title,
            "ctl00$ContentPlaceHolder1$txtCondition": condition,
            "ctl00$ContentPlaceHolder1$txtIntervention": intervention,
            "ctl00$ContentPlaceHolder1$ddlRecruitingStatus": "1",
            "ctl00$ContentPlaceHolder1$txtDateStart": date_start,
            "ctl00$ContentPlaceHolder1$txtDateEnd": date_end,
            "ctl00$ContentPlaceHolder1$btnSearch": "Search",
            "ctl00$ContentPlaceHolder1$postbacktextbox": "Advanced",
            "ctl00$ContentPlaceHolder1$postbacktextbox1": "True",
        })
        result = self._open(ADVANCED, urllib.parse.urlencode(form).encode())
        if re.search(r"NoAccess\.aspx|Error Page|application error|access denied", result, re.I):
            raise RuntimeError("WHO portal returned an application or access error page")
        parsed = _FormParser()
        parsed.feed(result)
        count_match = re.search(r"(\d+)\s+records?\s+for\s+\d+\s+trials?\s+found", result, re.I)
        if count_match is None and not parsed.trial_ids:
            raise RuntimeError("WHO portal response contained neither a result count nor trial IDs")
        total = int(count_match.group(1)) if count_match else len(parsed.trial_ids)
        if total > len(set(parsed.trial_ids)):
            raise RuntimeError(
                f"WHO portal query returned {total} records but only "
                f"{len(set(parsed.trial_ids))} were available on the page; pagination would truncate the delta"
            )
        time.sleep(self.delay)
        return list(dict.fromkeys(parsed.trial_ids)), total

    def trial(self, trial_id: str) -> dict[str, Any]:
        url = f"{PORTAL}/Trial2.aspx?{urllib.parse.urlencode({'TrialID': trial_id})}"
        parsed = _FormParser()
        parsed.feed(self._open(url))
        span = parsed.spans

        def value(suffix: str) -> str:
            return next((text for key, text in span.items() if key.endswith(suffix)), "")

        countries = [
            text for key, text in span.items() if "Country_Label" in key and text
        ]
        source_url = next(
            (href for key, href in parsed.links.items() if key.endswith("HyperLink12")), url
        )
        inclusion = value("Inclusion_criteriaLabel")
        exclusion = value("Exclusion_criteriaLabel")
        time.sleep(self.delay)
        return {
            "id": value("TrialIDLabel") or trial_id,
            "primary_registry_id": value("TrialIDLabel") or trial_id,
            "title": value("Public_titleLabel"),
            "scientific_title": value("Scientific_titleLabel"),
            "brief_summary": value("Brief_summaryLabel"),
            "overall_status": value("Recruitment_statusLabel"),
            "registration_date": value("Date_registrationLabel"),
            "last_update_date": value("Last_updatedLabel"),
            "countries": countries,
            "country_records": [
                {"country": country, "evidence_type": "who_portal_country"}
                for country in countries
            ],
            "disease_text": value("Condition_FreeTextLabel"),
            "interventions": [value("Intervention_FreeTextLabel")],
            "phases": [value("PhaseLabel")] if value("PhaseLabel") else [],
            "study_type": value("Study_typeLabel"),
            "source_url": source_url,
            "parsed_criteria": {
                "inclusion": [inclusion] if inclusion else [],
                "exclusion": [exclusion] if exclusion else [],
                "raw": "\n".join(part for part in (inclusion, exclusion) if part),
                "structured_demographics_status": "not_parsed_from_positional_portal_labels",
            },
            "portal_record_url": url,
        }


def _query_variants(plan: dict[str, Any]) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in plan.get("keyword_groups") or []:
        source = str(group.get("source") or "").strip().casefold()
        dimension = str(group.get("dimension") or "").strip()
        if dimension == "chinese_registry_terms" or source in {
            "chictr", "regional", "local_registry",
        }:
            continue
        label = str(group.get("label") or "unlabelled")
        conditions = list(dict.fromkeys(
            str(query.get("condition") or "").strip()
            for query in group.get("queries") or []
            if str(query.get("condition") or "").strip()
        ))
        terms = list(dict.fromkeys(
            str(query.get("term") or "").strip()
            for query in group.get("queries") or []
            if str(query.get("term") or "").strip()
        ))
        leaked = [value for value in conditions + terms if contains_cjk(value)]
        if leaked:
            raise ValueError(
                "WHO Portal search terms must be English; provide English aliases "
                f"for: {leaked}"
            )
        condition = " OR ".join(f"({item})" for item in conditions)
        term = " OR ".join(f"({item})" for item in terms)
        if len(condition) > 1000 or len(term) > 1000:
            raise ValueError(f"WHO portal combined query exceeds 1000 characters for group {label}")
        candidates = [{"condition": condition}]
        if term:
            candidates = [
                {"condition": condition, "intervention": term},
                {"condition": condition, "title": term},
                {"condition": f"({condition}) AND ({term})" if condition else term},
            ]
        for candidate in candidates:
            key = (
                candidate.get("title", ""),
                candidate.get("condition", ""),
                candidate.get("intervention", ""),
            )
            if key not in seen:
                seen.add(key)
                variants.append({"label": label, **candidate})
    return variants


def build_delta(
    *, database_as_of: str, plan: dict[str, Any], client: WhoPortalClient | None = None
) -> dict[str, Any]:
    watermark = dt.datetime.fromisoformat(database_as_of.replace("Z", "+00:00"))
    now = dt.datetime.now().astimezone()
    client = client or WhoPortalClient(
        timeout=float(os.environ.get("WHO_PORTAL_TIMEOUT_SECONDS", "60")),
        delay=float(os.environ.get("WHO_PORTAL_REQUEST_DELAY_SECONDS", "0.5")),
    )
    date_start, date_end = watermark.strftime("%d/%m/%Y"), now.strftime("%d/%m/%Y")
    ids: list[str] = []
    audit: list[dict[str, Any]] = []
    for variant in _query_variants(plan):
        found, total = client.search(
            title=variant.get("title", ""),
            condition=variant.get("condition", ""),
            intervention=variant.get("intervention", ""),
            date_start=date_start,
            date_end=date_end,
        )
        ids.extend(found)
        audit.append({
            **variant,
            "returned": len(found),
            "portal_total": total,
            "complete": len(found) == total,
        })
    unique_ids = list(dict.fromkeys(ids))
    trials = [client.trial(trial_id) for trial_id in unique_ids]
    return {
        "schema_version": "who-portal-delta-v1",
        "generator": "who_portal_delta.py",
        "search_plan_sha256": hashlib.sha256(
            json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "status": "executed",
        "database_as_of": database_as_of,
        "executed_at": now.isoformat(timespec="seconds"),
        "source": "WHO ICTRP public advanced search portal",
        "date_start": date_start,
        "date_end": date_end,
        "boundary_type": "registration_date_proxy",
        "query_audit": audit,
        "control_query": {"query_variants": len(audit), "complete": True},
        "trials": trials,
        "limitation": (
            "WHO portal registration-date filtering finds newly registered records but may miss "
            "older records modified after the database watermark."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-as-of", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
    payload = build_delta(database_as_of=args.database_as_of, plan=plan)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"trials": len(payload["trials"]), "output": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
