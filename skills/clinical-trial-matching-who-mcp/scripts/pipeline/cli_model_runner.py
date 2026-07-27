"""Adapter from a stdin/stdout agent CLI to the deterministic batch executor."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def _command() -> list[str]:
    raw = os.environ.get("MODEL_AGENT_COMMAND_JSON", "")
    if not raw:
        raise ValueError(
            "MODEL_AGENT_COMMAND_JSON is required, for example "
            "'[\"claude\",\"-p\",\"--output-format\",\"text\"]'"
        )
    value = json.loads(raw)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError("MODEL_AGENT_COMMAND_JSON must be a non-empty JSON array of strings")
    return value


def _json_payload(text: str) -> dict:
    candidates = [text.strip()]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Agent CLI did not return one strict JSON object")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    envelope = json.loads(Path(args.input).read_text(encoding="utf-8"))
    prompt = (
        "Execute the attached clinical-analysis job exactly. Read every referenced SKILL.md. "
        "Do not omit or select trials. Return only the required JSON object.\n\n"
        + json.dumps(envelope, ensure_ascii=False)
    )
    timeout = float(os.environ.get("MODEL_AGENT_TIMEOUT_SECONDS", "1800"))
    completed = subprocess.run(
        _command(), input=prompt, text=True, capture_output=True, timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Agent CLI exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout)[-1000:]}"
        )
    payload = _json_payload(completed.stdout)
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
