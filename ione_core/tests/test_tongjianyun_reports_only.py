import sys
import unittest
from types import ModuleType
from unittest.mock import patch

from ione_core.mcp.tongjianyun_analysis import generate_tongjianyun_recipe_analysis
from ione_core.mcp.tongjianyun_recipe import upsert_tongjianyun_recipe


class ReportsOnlyBoundaryTests(unittest.TestCase):
	def test_retired_mcp_mutations_fail_before_permissions_or_storage(self):
		frappe = ModuleType("frappe")
		frappe.get_installed_apps = lambda: ["frappe", "tongjianyun"]
		package = ModuleType("tongjianyun")
		package.REPORTS_ONLY = True
		with patch.dict(sys.modules, {"frappe": frappe, "tongjianyun": package}):
			for call, args in ((generate_tongjianyun_recipe_analysis, ("ANY-RECIPE",)), (upsert_tongjianyun_recipe, ({}, []))):
				with self.subTest(call=call.__name__), self.assertRaisesRegex(ValueError, "童健云"):
					call(*args)
