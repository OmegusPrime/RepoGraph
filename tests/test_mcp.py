import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class McpServerTests(unittest.TestCase):
    def test_server_initializes_and_lists_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            payload = "\n".join(json.dumps(request) for request in requests) + "\n"
            environment = os.environ.copy()
            environment["REPOGRAPH_ROOT"] = str(Path(directory))
            result = subprocess.run(
                [sys.executable, "-m", "repograph.mcp_server"],
                input=payload,
                text=True,
                capture_output=True,
                env=environment,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(responses[0]["result"]["serverInfo"]["version"], "0.3.5")
            tools = {tool["name"] for tool in responses[1]["result"]["tools"]}
            self.assertIn("graph_search", tools)
            self.assertIn("proposed_change_impact", tools)


if __name__ == "__main__":
    unittest.main()
