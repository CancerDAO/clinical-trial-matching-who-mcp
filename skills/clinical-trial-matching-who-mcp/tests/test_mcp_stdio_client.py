from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))

from mcp_stdio_client import JsonRpcMcpClient, McpClientError


class JsonRpcMcpClientTests(unittest.TestCase):
    def _server(self, source: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        script = directory / "server.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        self.addCleanup(shutil.rmtree, directory, True)
        return script

    def test_ignores_non_json_stdout_before_response(self):
        server = self._server("""
            import json, sys
            request = json.loads(sys.stdin.readline())
            print("server startup log", flush=True)
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}), flush=True)
        """)
        client = JsonRpcMcpClient(sys.executable, [str(server)], os.environ.copy(), request_timeout=2)
        self.addCleanup(client.close)
        self.assertEqual(client.request("ping"), {"ok": True})

    def test_timeout_has_method_and_duration(self):
        server = self._server("""
            import sys, time
            sys.stdin.readline()
            time.sleep(0.3)
        """)
        client = JsonRpcMcpClient(sys.executable, [str(server)], os.environ.copy(), request_timeout=0.1)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(McpClientError, "ping.*timed out after 0.1s"):
            client.request("ping")

    def test_timeout_is_not_reset_by_unrelated_messages(self):
        server = self._server("""
            import json, sys, time
            sys.stdin.readline()
            for _ in range(50):
                print(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}), flush=True)
                time.sleep(0.01)
        """)
        client = JsonRpcMcpClient(sys.executable, [str(server)], os.environ.copy(), request_timeout=0.1)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(McpClientError, "timed out after 0.1s"):
            client.request("ping")
