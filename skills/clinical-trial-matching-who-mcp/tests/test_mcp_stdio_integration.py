from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))
from mcp_http_client import run_remote_who_workflow
from mcp_stdio_client import run_who_workflow


class RealMcpStdioIntegrationTests(unittest.TestCase):
    def test_initialize_list_tools_search_and_get_trial_cross_process(self):
        transport = os.environ.get("WHO_MCP_TRANSPORT", "stdio").strip().casefold()
        plan = {
            "keyword_groups": [{
                "label": "disease biomarker",
                "queries": [{"condition": "colorectal cancer", "term": "KRAS G12C"}],
            }]
        }
        if transport in {"http", "streamable-http"}:
            url = os.environ.get("WHO_MCP_URL", "")
            api_key = os.environ.get("WHO_MCP_API_KEY", "")
            if not (url and api_key):
                self.skipTest("Set WHO_MCP_URL and WHO_MCP_API_KEY to run remote MCP integration")
            result = run_remote_who_workflow(
                url=url, api_key=api_key, search_plan=plan, max_per_query=2, total_limit=3,
            )
            self.assertEqual(result["transport"], "streamable_http_mcp_jsonrpc")
        else:
            python = Path(os.environ.get("WHO_MCP_PYTHON", sys.executable))
            server_value = os.environ.get("WHO_MCP_SERVER")
            database_value = os.environ.get("WHO_MCP_DB")
            if not (server_value and database_value):
                self.skipTest("Set WHO_MCP_SERVER and WHO_MCP_DB to run stdio MCP integration")
            server = Path(server_value)
            database = Path(database_value)
            if not (python.exists() and server.exists() and database.exists()):
                self.skipTest("Configured real-MCP integration dependencies are unavailable")
            result = run_who_workflow(
                server_python=str(python), server_script=server, database=database,
                search_plan=plan, max_per_query=2, total_limit=3,
            )
            self.assertEqual(result["transport"], "stdio_mcp_jsonrpc")
        self.assertEqual(result["protocol_version"], "2024-11-05")
        self.assertIn("execute_search_plan", result["server_tools"])
        self.assertGreater(len(result["search"]["results"]), 0)
        self.assertEqual(len(result["details"]), len(result["search"]["results"]))
        self.assertTrue(all(detail.get("found") for detail in result["details"]))
        self.assertTrue(result["metadata"].get("database_as_of"))


if __name__ == "__main__":
    unittest.main()
