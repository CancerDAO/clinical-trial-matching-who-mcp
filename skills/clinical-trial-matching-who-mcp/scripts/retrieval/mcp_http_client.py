"""Authenticated MCP Streamable HTTP client for the formal matching workflow."""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from mcp_transport import McpClientError, execute_who_workflow


class JsonRpcHttpMcpClient:
    def __init__(self, url: str, api_key: str, timeout: float | None = None):
        parsed = urlparse(url)
        allow_insecure = os.environ.get("WHO_MCP_ALLOW_INSECURE_HTTP") == "1"
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise McpClientError("WHO_MCP_URL must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and not allow_insecure:
            raise McpClientError("Remote MCP requires HTTPS; set WHO_MCP_ALLOW_INSECURE_HTTP=1 only for a trusted private network")
        if not api_key:
            raise McpClientError("WHO_MCP_API_KEY is required for Streamable HTTP")
        self.url = url
        self.api_key = api_key
        self.timeout = timeout or float(os.environ.get("MCP_REQUEST_TIMEOUT_SECONDS", "60"))
        self.request_id = 0
        self.protocol_version = "2024-11-05"
        self.session_id: str | None = None
        self._state_lock = threading.Lock()

    @staticmethod
    def _retry_settings() -> tuple[int, float]:
        try:
            retries = int(os.environ.get("MCP_TRANSIENT_RETRIES", "4"))
            delay = float(os.environ.get("MCP_RETRY_BASE_SECONDS", "1"))
        except ValueError as exc:
            raise McpClientError(
                "MCP_TRANSIENT_RETRIES and MCP_RETRY_BASE_SECONDS must be numeric"
            ) from exc
        if retries < 0 or retries > 10:
            raise McpClientError("MCP_TRANSIENT_RETRIES must be between 0 and 10")
        if delay < 0 or delay > 30:
            raise McpClientError("MCP_RETRY_BASE_SECONDS must be between 0 and 30")
        return retries, delay

    @staticmethod
    def _sse_messages(body: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for event in body.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(
                line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
            )
            if not data:
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                messages.append(parsed)
        return messages

    def _post(self, payload: dict[str, Any], notification: bool = False) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol_version,
        }
        with self._state_lock:
            session_id = self.session_id
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        max_retries, base_delay = self._retry_settings()
        attempt = 0
        while True:
            request = Request(self.url, data=data, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    content_type = response.headers.get("Content-Type", "")
                    returned_session = response.headers.get("Mcp-Session-Id")
                    if returned_session:
                        with self._state_lock:
                            self.session_id = returned_session
                break
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in {502, 503, 504} and attempt < max_retries:
                    attempt += 1
                    time.sleep(min(base_delay * attempt, 30))
                    continue
                raise McpClientError(
                    f"Remote MCP HTTP {exc.code} after {attempt + 1} attempt(s): "
                    f"{detail or exc.reason}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt < max_retries:
                    attempt += 1
                    time.sleep(min(base_delay * attempt, 30))
                    continue
                raise McpClientError(
                    f"Remote MCP request failed after {attempt + 1} attempt(s): {exc}"
                ) from exc
        if notification and not body.strip():
            return None
        if "text/event-stream" in content_type:
            messages = self._sse_messages(body)
            expected_id = payload.get("id")
            message = next((item for item in messages if item.get("id") == expected_id), None)
            if message is None:
                raise McpClientError("Remote MCP SSE stream did not contain the expected JSON-RPC response")
            return message
        try:
            message = json.loads(body)
        except json.JSONDecodeError as exc:
            raise McpClientError("Remote MCP returned non-JSON content") from exc
        if not isinstance(message, dict):
            raise McpClientError("Remote MCP returned a non-object JSON-RPC message")
        return message

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._state_lock:
            self.request_id += 1
            request_id = self.request_id
        message = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        if not message or message.get("id") != request_id:
            raise McpClientError(f"Remote MCP returned an unexpected response id for {method}")
        if "error" in message:
            raise McpClientError(f"Remote MCP error for {method}: {message['error']}")
        return message.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params or {}}, notification=True)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = "\n".join(item.get("text", "") for item in result.get("content") or [])
            raise McpClientError(f"Remote MCP tool {name} failed: {text}")
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        text = "\n".join(
            item.get("text", "") for item in result.get("content") or [] if item.get("type") == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpClientError(f"Remote MCP tool {name} returned non-JSON content") from exc


def run_remote_who_workflow(
    *, url: str, api_key: str, search_plan: dict[str, Any],
    max_per_query: int, total_limit: int,
) -> dict[str, Any]:
    client = JsonRpcHttpMcpClient(url, api_key)

    def load_details(registry_ids: list[str]) -> list[dict[str, Any]]:
        try:
            detail_workers = max(1, int(os.environ.get("MCP_DETAIL_CONCURRENCY", "8")))
        except ValueError as exc:
            raise McpClientError("MCP_DETAIL_CONCURRENCY must be an integer") from exc
        detail_workers = min(detail_workers, 32)
        with ThreadPoolExecutor(max_workers=detail_workers) as pool:
            return list(pool.map(
                lambda registry_id: client.call_tool(
                    "get_trial", {"registry_id": registry_id}
                ),
                registry_ids,
            ))

    return execute_who_workflow(
        client,
        transport_name="streamable_http_mcp_jsonrpc",
        client_version="3.2",
        search_plan=search_plan,
        max_per_query=max_per_query,
        total_limit=total_limit,
        detail_loader=load_details,
    )
