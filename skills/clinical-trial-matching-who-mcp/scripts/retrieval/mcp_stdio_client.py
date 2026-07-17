"""MCP JSON-RPC stdio client used by the formal matching workflow."""
from __future__ import annotations

import argparse
from collections import deque
import json
import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mcp_transport import McpClientError, execute_who_workflow


class JsonRpcMcpClient:
    def __init__(self, command: str, args: list[str], env: dict[str, str], request_timeout: float | None = None):
        self.process = subprocess.Popen(
            [command, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1,
        )
        self.request_id = 0
        self.request_timeout = request_timeout or float(os.environ.get("MCP_REQUEST_TIMEOUT_SECONDS", "60"))
        self._stdout: queue.Queue[str | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        if not self.process.stdout:
            self._stdout.put(None)
            return
        for line in self.process.stdout:
            self._stdout.put(line)
        self._stdout.put(None)

    def _read_stderr(self) -> None:
        if self.process.stderr:
            for line in self.process.stderr:
                self._stderr_tail.append(line.rstrip())

    def _diagnostic(self) -> str:
        return "\n".join(self._stderr_tail)[-1000:]

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.process.stdin:
            raise McpClientError("MCP stdin is unavailable")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.request_id += 1
        request_id = self.request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        if not self.process.stdout:
            raise McpClientError("MCP stdout is unavailable")
        deadline = time.monotonic() + self.request_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = self._diagnostic()
                suffix = f"; server stderr: {detail}" if detail else ""
                raise McpClientError(
                    f"MCP request {method!r} timed out after {self.request_timeout:g}s{suffix}"
                )
            try:
                line = self._stdout.get(timeout=remaining)
            except queue.Empty as exc:
                detail = self._diagnostic()
                suffix = f"; server stderr: {detail}" if detail else ""
                raise McpClientError(
                    f"MCP request {method!r} timed out after {self.request_timeout:g}s{suffix}"
                ) from exc
            if line is None:
                detail = self._diagnostic()
                raise McpClientError(f"MCP server exited unexpectedly: {detail or 'no stderr output'}")
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                logging.getLogger(__name__).warning(
                    "Ignoring non-JSON line emitted on MCP stdout"
                )
                continue
            if not isinstance(message, dict):
                logging.getLogger(__name__).warning(
                    "Ignoring non-object JSON message emitted on MCP stdout"
                )
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpClientError(f"MCP error for {method}: {message['error']}")
            return message.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = "\n".join(item.get("text", "") for item in result.get("content") or [])
            raise McpClientError(f"MCP tool {name} failed: {text}")
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        text = "\n".join(item.get("text", "") for item in result.get("content") or [] if item.get("type") == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpClientError(f"MCP tool {name} returned non-JSON content") from exc

    def close(self) -> None:
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=5)
        except Exception:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
        finally:
            for stream in (self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()


def run_who_workflow(
    *, server_python: str, server_script: Path, database: Path,
    search_plan: dict[str, Any], max_per_query: int, total_limit: int,
) -> dict[str, Any]:
    client = JsonRpcMcpClient(
        server_python,
        [str(server_script)],
        {
            **os.environ,
            "WHO_ICTRP_DB": str(database),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    client.protocol_version = "2024-11-05"
    try:
        return execute_who_workflow(
            client,
            transport_name="stdio_mcp_jsonrpc",
            client_version="3.2",
            search_plan=search_plan,
            max_per_query=max_per_query,
            total_limit=total_limit,
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a search plan through the WHO MCP stdio server")
    parser.add_argument("--server-python", required=True)
    parser.add_argument("--server-script", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-per-query", type=int, default=5000)
    parser.add_argument("--total-limit", type=int, default=20000)
    args = parser.parse_args()
    payload = run_who_workflow(
        server_python=args.server_python, server_script=Path(args.server_script), database=Path(args.db),
        search_plan=json.loads(Path(args.plan).read_text(encoding="utf-8-sig")),
        max_per_query=args.max_per_query, total_limit=args.total_limit,
    )
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
