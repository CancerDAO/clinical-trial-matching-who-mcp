"""Transport-neutral orchestration for the WHO MCP tool contract."""
from __future__ import annotations

from typing import Any, Callable, Protocol


class McpClientError(RuntimeError):
    """An identifiable MCP transport or protocol failure."""


class McpTransport(Protocol):
    protocol_version: str

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any: ...

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


DetailLoader = Callable[[list[str]], list[dict[str, Any]]]


def audit_search_completeness(
    search: dict[str, Any], *, max_per_query: int, total_limit: int
) -> dict[str, Any]:
    """Normalize completeness flags, including responses from older MCP servers."""
    stats = dict(search.get("search_stats") or {})
    query_audit = [dict(item) for item in search.get("query_audit") or []]
    inferred_queries: list[dict[str, Any]] = []
    for item in query_audit:
        returned = int(item.get("returned") or 0)
        query_limit = int(item.get("max_per_query") or max_per_query)
        explicitly_complete = (
            item.get("has_more") is False
            or item.get("complete") is True
            or item.get("exhausted") is True
        )
        if returned >= query_limit and not explicitly_complete:
            item["truncated"] = True
            item["truncation_inferred"] = True
            inferred_queries.append({
                "label": item.get("label"),
                "condition": item.get("condition"),
                "term": item.get("term"),
                "returned": returned,
                "limit": query_limit,
            })

    returned_total = int(stats.get("returned") or len(search.get("results") or []))
    explicitly_globally_complete = (
        stats.get("has_more") is False
        or stats.get("complete") is True
        or stats.get("exhausted") is True
    )
    if returned_total >= total_limit and not explicitly_globally_complete:
        stats["global_truncated"] = True
        stats["global_truncation_inferred"] = True
    stats["query_truncation_count"] = sum(
        bool(item.get("truncated")) for item in query_audit
    )
    if inferred_queries:
        stats["inferred_truncated_queries"] = inferred_queries
    search["search_stats"] = stats
    search["query_audit"] = query_audit
    return search


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
    search = client.call_tool("execute_search_plan", {
        "search_plan": search_plan,
        "country": "",
        "max_per_query": max_per_query,
        "total_limit": total_limit,
    })
    search = audit_search_completeness(
        search, max_per_query=max_per_query, total_limit=total_limit
    )
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
    }
