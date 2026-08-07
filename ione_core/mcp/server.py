from ione_core.mcp.runtime import MCP

mcp = MCP(name="ione-manager")


@mcp.register(allow_guest=False)
def handle_mcp():
	"""Serve the I-ONE manager MCP endpoint for authenticated Frappe users."""
	from ione_core.mcp import tools  # noqa: F401
