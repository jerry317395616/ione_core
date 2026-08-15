import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.tongjianyun_analysis import generate_tongjianyun_recipe_analysis


class TestTongjianyunAnalysisMCP(TestCase):
	def test_checks_recipe_permissions_before_generating(self):
		frappe = ModuleType("frappe")
		frappe.get_installed_apps = lambda: ["frappe", "tongjianyun"]
		doc = SimpleNamespace(name="2026-W17", check_permission=lambda permission: permissions.append(("doc", permission)))
		frappe.get_doc = lambda doctype, name: doc
		package = ModuleType("tongjianyun")
		package.__path__ = []
		analysis = ModuleType("tongjianyun.recipe_analysis")
		analysis.create_and_attach_recipe_analysis = lambda name, standard=None: {"recipe": name, "download_url": "/private/files/report.xlsx"}
		permissions = []
		with (
			patch.dict(sys.modules, {"frappe": frappe, "tongjianyun": package, "tongjianyun.recipe_analysis": analysis}),
			patch("ione_core.mcp.tongjianyun_analysis.ensure_doctype_permission", side_effect=lambda dt, p: permissions.append((dt, p))),
		):
			result = generate_tongjianyun_recipe_analysis("2026-W17")
		self.assertEqual(result["recipe"], "2026-W17")
		self.assertEqual(permissions, [("Tongjianyun Recipe", "read"), ("doc", "read")])
