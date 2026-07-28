import sys
import types
from unittest import TestCase
from unittest.mock import MagicMock, patch

try:
	import frappe  # type: ignore[import-not-found]
except ModuleNotFoundError:
	frappe = types.ModuleType("frappe")
	frappe.db = MagicMock()
	frappe.db.exists.return_value = False
	frappe.defaults = MagicMock()
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.utils = types.ModuleType("frappe.utils")
	frappe.utils.add_days = MagicMock()
	frappe.utils.add_months = MagicMock()
	frappe.utils.get_first_day = MagicMock()
	frappe.utils.get_last_day = MagicMock()
	frappe.utils.now_datetime = MagicMock()
	frappe.utils.today = MagicMock(return_value="2026-07-28")
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = frappe.utils

from ione_core.business_seed import CORE_COVERAGE, SeedReport, _delivery_quantity


class TestBusinessSeed(TestCase):
	def test_report_is_json_serializable(self):
		report = SeedReport(
			created=["ToDo: sample"],
			existing=["Company: demo"],
			skipped=["Drive: external storage"],
			errors={"CRM": "failed"},
		)

		with patch("ione_core.business_seed.get_business_data_coverage", return_value={}):
			data = report.as_dict()

		self.assertEqual(data["created"], ["ToDo: sample"])
		self.assertEqual(data["errors"]["CRM"], "failed")

	def test_coverage_defines_all_installed_business_surfaces(self):
		for domain in (
			"销售管理",
			"采购管理",
			"库存管理",
			"人力资源",
			"CRM",
			"服务台",
			"学习",
			"借贷",
			"Gameplan",
			"内容协作",
			"数据分析",
			"Drive",
			"Telephony",
			"智能执行",
		):
			self.assertIn(domain, CORE_COVERAGE)

	def test_inventory_coverage_includes_delivery_notes(self):
		self.assertIn("Delivery Note", CORE_COVERAGE["库存管理"])

	def test_delivery_quantity_stays_conservative(self):
		self.assertEqual(_delivery_quantity(13), 1)
		self.assertEqual(_delivery_quantity(200), 10)
		self.assertEqual(_delivery_quantity(2000), 10)
