"""Transport-neutral orchestration for the WHO MCP tool contract."""
from __future__ import annotations

import os
from typing import Any, Callable, Protocol

from search_plan import compile_search_plan_for_mcp

class McpClientError(RuntimeError):
    """An identifiable MCP transport or protocol failure."""


class McpTransport(Protocol):
    protocol_version: str

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any: ...

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


DetailLoader = Callable[[list[str]], list[dict[str, Any]]]


def execute_who_workflow(
    client: McpTransport,
    *,
    transport_name: str,
    client_version: str,
    search_plan: dict[str, Any],
    max_per_query: int,
    total_limit: int,
    detail_loader: DetailLoader | None = None,
) -> dict[str, Any]:
    """Run the shared WHO MCP tool sequence over any conforming transport."""
    initialized = client.request("initialize", {
        "protocolVersion": client.protocol_version,
        "capabilities": {},
        "clientInfo": {
            "name": "clinical-trial-matching-who-mcp",
            "version": client_version,
        },
    })
    negotiated = initialized.get("protocolVersion") or client.protocol_version
    client.protocol_version = negotiated
    client.notify("notifications/initialized")

    listed = client.request("tools/list")
    names = {tool["name"] for tool in listed.get("tools") or []}
    required = {"database_metadata", "execute_search_plan", "get_trial"}
    missing = sorted(required - names)
    if missing:
        raise McpClientError(f"WHO MCP server missing tools: {missing}")

    metadata = client.call_tool("database_metadata", {})
    executed_search_plan = compile_search_plan_for_mcp(search_plan)
    search_arguments = {
        "search_plan": executed_search_plan,
        "country": "",
        "max_per_query": max_per_query,
        "total_limit": total_limit,
    }
    search = client.call_tool("execute_search_plan", search_arguments)
    try:
        zero_result_retries = max(0, min(2, int(os.environ.get(
            "MCP_ZERO_RESULT_RETRIES", "1"
        ))))
    except ValueError as exc:
        raise McpClientError("MCP_ZERO_RESULT_RETRIES must be an integer") from exc
    retry_count = 0
    while not (search.get("results") or []) and retry_count < zero_result_retries:
        retry_count += 1
        search = client.call_tool("execute_search_plan", search_arguments)
    search.setdefault("retrieval_resilience_audit", {})
    search["retrieval_resilience_audit"].update({
        "zero_result_retry_count": retry_count,
        "zero_result_after_retry": not bool(search.get("results") or []),
    })
    stats = search.get("search_stats") or {}
    audit = search.get("query_audit") or []
    if stats.get("global_truncated") or stats.get("query_truncation_count"):
        raise McpClientError("WHO MCP search reported truncated results")
    if audit and any(
        item.get("truncated") is True
        or item.get("has_more") is True
        or item.get("complete") is False
        for item in audit
        if isinstance(item, dict)
    ):
        raise McpClientError("WHO MCP query audit is missing or incomplete")
    registry_ids = list(dict.fromkeys(
        registry_id
        for hit in search.get("results") or []
        if (registry_id := str(hit.get("primary_registry_id") or hit.get("id") or "").strip())
    ))
    fetch_details = os.environ.get("MCP_FETCH_DETAILS", "1").strip() != "0"
    if not fetch_details:
        details: list[dict[str, Any]] = []
    elif detail_loader is None:
        details = [
            client.call_tool("get_trial", {"registry_id": registry_id})
            for registry_id in registry_ids
        ]
    else:
        details = detail_loader(registry_ids)

    return {
        "transport": transport_name,
        "protocol_version": negotiated,
        "server_info": initialized.get("serverInfo"),
        "server_tools": sorted(names),
        "metadata": metadata,
        "search": search,
        "details": details,
        "registry_ids": registry_ids,
        "executed_search_plan": executed_search_plan,
    }


def load_trial_details(
    client: McpTransport,
    registry_ids: list[str],
    detail_loader: DetailLoader | None = None,
) -> list[dict[str, Any]]:
    """Fetch get_trial payloads for a selected ID set after recall triage."""
    unique = list(dict.fromkeys(str(value).strip() for value in registry_ids if str(value).strip()))
    if not unique:
        return []
    if detail_loader is None:
        return [
            client.call_tool("get_trial", {"registry_id": registry_id})
            for registry_id in unique
        ]
    return detail_loader(unique)
