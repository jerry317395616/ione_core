from unittest import TestCase

from ione_core.mcp.runtime import MCP, ToolAnnotations


class TestMCPRuntime(TestCase):
	def setUp(self):
		self.mcp = MCP("test-server", version="1.2.3")

		@self.mcp.tool(
			annotations=ToolAnnotations(
				readOnlyHint=True,
				destructiveHint=False,
				idempotentHint=True,
				openWorldHint=False,
			)
		)
		def greet(name: str, limit: int = 1) -> dict:
			"""Return a greeting.

			Args:
				name: Person to greet.
				limit: Number of greetings.
			"""
			return {"message": " ".join([f"Hello {name}"] * limit)}

	def request(self, method, params=None, request_id=1):
		return self.mcp.process(
			{"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
		)

	def test_initialize_negotiates_supported_protocol(self):
		response = self.request("initialize", {"protocolVersion": "2025-06-18"})
		self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
		self.assertEqual(response["result"]["serverInfo"]["name"], "test-server")

	def test_lists_tool_schema_and_annotations(self):
		tool = self.request("tools/list")["result"]["tools"][0]
		self.assertEqual(tool["name"], "greet")
		self.assertEqual(tool["inputSchema"]["required"], ["name"])
		self.assertEqual(tool["inputSchema"]["properties"]["limit"]["type"], "integer")
		self.assertTrue(tool["annotations"]["readOnlyHint"])

	def test_calls_tool_and_returns_structured_content(self):
		result = self.request("tools/call", {"name": "greet", "arguments": {"name": "I-ONE", "limit": 2}})[
			"result"
		]
		self.assertFalse(result["isError"])
		self.assertEqual(result["structuredContent"]["message"], "Hello I-ONE Hello I-ONE")

	def test_rejects_missing_required_arguments(self):
		response = self.request("tools/call", {"name": "greet", "arguments": {}})
		self.assertEqual(response["error"]["code"], -32602)

	def test_notification_has_no_response(self):
		self.assertIsNone(self.mcp.process({"jsonrpc": "2.0", "method": "notifications/initialized"}))
