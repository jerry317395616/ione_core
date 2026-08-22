import sys
from importlib import import_module
from types import ModuleType


def test_mcp_server_loads_tool_modules_from_frappe_hooks(monkeypatch) -> None:
	fake_frappe = ModuleType("frappe")
	fake_frappe.whitelist = lambda **_kwargs: lambda function: function
	fake_frappe.get_hooks = lambda name: (
		["example.nutrition_tools"] if name == "ione_mcp_tool_modules" else []
	)
	monkeypatch.setitem(sys.modules, "frappe", fake_frappe)

	server = import_module("ione_core.mcp.server")
	loaded = []
	monkeypatch.setattr(server, "import_module", loaded.append)

	server._load_extension_tools()

	assert loaded == ["example.nutrition_tools"]
