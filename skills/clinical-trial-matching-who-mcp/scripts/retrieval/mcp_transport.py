"""Transport-neutral orchestration for the WHO MCP tool contract."""
from __future__ import annotations

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
    search = client.call_tool("execute_search_plan", {
        "search_plan": executed_search_plan,
        "country": "",
        "max_per_query": max_per_query,
        "total_limit": total_limit,
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
    registry_ids = [
        registry_id
        for hit in search.get("results") or []
        if (registry_id := hit.get("primary_registry_id") or hit.get("id"))
    ]
    if detail_loader is None:
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
        "executed_search_plan": executed_search_plan,
    }
