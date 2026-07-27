from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))

from mcp_http_client import JsonRpcHttpMcpClient, run_remote_who_workflow
from mcp_transport import audit_search_completeness
from mcp_stdio_client import McpClientError


class FakeMcpHandler(BaseHTTPRequestHandler):
    api_key = "test-secret"
    session_id = "test-session"
    lock = threading.Lock()
    active_details = 0
    max_active_details = 0
    saw_session_header = False
    transient_failures_remaining = 0

    def log_message(self, format, *args):
        return

    def _reply(self, status, payload=None, *, content_type="application/json", headers=None):
        body = payload if isinstance(payload, bytes) else (
            json.dumps(payload).encode() if payload is not None else b""
        )
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if body:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.headers.get("Authorization") != f"Bearer {self.api_key}":
            self._reply(401, {"error": "unauthorized"})
            return
        message = json.loads(body)
        request_id = message.get("id")
        method = message["method"]

        if method != "initialize":
            if self.headers.get("Mcp-Session-Id") != self.session_id:
                self._reply(400, {"error": "missing session"})
                return
            type(self).saw_session_header = True

        if request_id is None:
            self._reply(202)
            return

        if method == "tools/call" and type(self).transient_failures_remaining:
            type(self).transient_failures_remaining -= 1
            self._reply(502, {"error": "temporary upstream failure"})
            return

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "serverInfo": {"name": "fake-who-mcp", "version": "1"},
            }
            self._reply(
                200,
                {"jsonrpc": "2.0", "id": request_id, "result": result},
                headers={"Mcp-Session-Id": self.session_id},
            )
            return

        if method == "tools/list":
            result = {"tools": [{"name": name} for name in (
                "database_metadata", "execute_search_plan", "get_trial"
            )]}
            progress = json.dumps({
                "jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}
            })
            response = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})
            body = f"event: message\ndata: {progress}\n\nevent: message\ndata: {response}\n\n".encode()
            self._reply(200, body, content_type="text/event-stream")
            return

        if method != "tools/call":
            self._reply(200, {
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "unknown method"},
            })
            return

        name = message["params"]["name"]
        if name == "database_metadata":
            content = {"database_as_of": "2026-07-16T00:00:00+00:00"}
        elif name == "execute_search_plan":
            content = {
                "results": [
                    {"id": "NCT1", "primary_registry_id": "NCT1"},
                    {"id": "NCT2", "primary_registry_id": "NCT2"},
                    {"id": "NCT3", "primary_registry_id": "NCT3"},
                ],
                "search_stats": {},
            }
        elif name == "get_trial":
            registry_id = message["params"]["arguments"]["registry_id"]
            with self.lock:
                type(self).active_details += 1
                type(self).max_active_details = max(
                    type(self).max_active_details, type(self).active_details
                )
            time.sleep(0.04)
            with self.lock:
                type(self).active_details -= 1
            content = {"id": registry_id, "found": True}
        else:
            self._reply(200, {
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "unknown tool"},
            })
            return

        result = {"structuredContent": content, "content": [], "isError": False}
        self._reply(200, {"jsonrpc": "2.0", "id": request_id, "result": result})


class StreamableHttpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/mcp"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        FakeMcpHandler.active_details = 0
        FakeMcpHandler.max_active_details = 0
        FakeMcpHandler.saw_session_header = False
        FakeMcpHandler.transient_failures_remaining = 0

    def test_complete_remote_workflow_uses_session_sse_and_concurrency(self):
        with patch.dict("os.environ", {"MCP_DETAIL_CONCURRENCY": "3"}):
            result = run_remote_who_workflow(
                url=self.url,
                api_key=FakeMcpHandler.api_key,
                search_plan={"keyword_groups": []},
                max_per_query=2,
                total_limit=3,
            )
        self.assertEqual(result["transport"], "streamable_http_mcp_jsonrpc")
        self.assertEqual(result["metadata"]["database_as_of"], "2026-07-16T00:00:00+00:00")
        self.assertEqual([item["id"] for item in result["details"]], ["NCT1", "NCT2", "NCT3"])
        self.assertTrue(FakeMcpHandler.saw_session_header)
        self.assertGreater(FakeMcpHandler.max_active_details, 1)

    def test_old_server_exact_query_cap_is_conservatively_marked_truncated(self):
        search = audit_search_completeness({
            "results": [{"id": "NCT1"}],
            "search_stats": {"returned": 1},
            "query_audit": [{
                "label": "broad",
                "returned": 40,
                "max_per_query": 40,
                "truncated": False,
            }],
        }, max_per_query=40, total_limit=300)
        self.assertEqual(search["search_stats"]["query_truncation_count"], 1)
        self.assertTrue(search["query_audit"][0]["truncation_inferred"])

    def test_explicit_complete_query_at_cap_is_not_marked_truncated(self):
        search = audit_search_completeness({
            "results": [{"id": "NCT1"}],
            "search_stats": {"returned": 1, "complete": True},
            "query_audit": [{
                "label": "narrow",
                "returned": 40,
                "max_per_query": 40,
                "truncated": False,
                "complete": True,
                "has_more": False,
            }],
        }, max_per_query=40, total_limit=300)
        self.assertEqual(search["search_stats"]["query_truncation_count"], 0)

    def test_wrong_api_key_is_identifiable(self):
        client = JsonRpcHttpMcpClient(self.url, "wrong", timeout=1)
        with self.assertRaisesRegex(McpClientError, "HTTP 401"):
            client.request("initialize")

    def test_transient_502_is_retried(self):
        client = JsonRpcHttpMcpClient(self.url, FakeMcpHandler.api_key, timeout=1)
        client.request("initialize")
        client.notify("notifications/initialized")
        FakeMcpHandler.transient_failures_remaining = 2
        with patch.dict("os.environ", {
            "MCP_TRANSIENT_RETRIES": "2",
            "MCP_RETRY_BASE_SECONDS": "0",
        }):
            result = client.call_tool("database_metadata", {})
        self.assertEqual(result["database_as_of"], "2026-07-16T00:00:00+00:00")
        self.assertEqual(FakeMcpHandler.transient_failures_remaining, 0)

    def test_retryable_status_set_covers_gateway_failures(self):
        client = JsonRpcHttpMcpClient(self.url, FakeMcpHandler.api_key, timeout=1)
        for status_code in (502, 503, 504):
            error = __import__("urllib.error").error.HTTPError(
                self.url, status_code, "temporary", {}, BytesIO(b"temporary")
            )
            with patch("mcp_http_client.urlopen", side_effect=[
                error,
                mock_response := MagicMock(),
            ]):
                mock_response.__enter__.return_value.read.return_value = (
                    b'{"jsonrpc":"2.0","id":1,"result":{}}'
                )
                mock_response.__enter__.return_value.headers = {}
                with patch.dict("os.environ", {
                    "MCP_TRANSIENT_RETRIES": "1",
                    "MCP_RETRY_BASE_SECONDS": "0",
                }):
                    response = client._post({
                        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}
                    })
            self.assertEqual(response["result"], {})

    def test_non_transient_401_is_not_retried(self):
        client = JsonRpcHttpMcpClient(self.url, "wrong", timeout=1)
        with patch.dict("os.environ", {
            "MCP_TRANSIENT_RETRIES": "4",
            "MCP_RETRY_BASE_SECONDS": "0",
        }):
            with self.assertRaisesRegex(McpClientError, "after 1 attempt"):
                client.request("initialize")

    def test_plain_http_is_rejected_for_remote_hosts(self):
        with self.assertRaisesRegex(McpClientError, "requires HTTPS"):
            JsonRpcHttpMcpClient("http://mcp.example.org/mcp", "secret")

    def test_invalid_detail_concurrency_is_identifiable(self):
        with patch.dict("os.environ", {"MCP_DETAIL_CONCURRENCY": "many"}):
            with self.assertRaisesRegex(McpClientError, "must be an integer"):
                run_remote_who_workflow(
                    url=self.url,
                    api_key=FakeMcpHandler.api_key,
                    search_plan={"keyword_groups": []},
                    max_per_query=2,
                    total_limit=3,
                )


if __name__ == "__main__":
    unittest.main()
