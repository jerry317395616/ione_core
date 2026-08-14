import csv
from pathlib import Path
from unittest import TestCase

from ione_core import hooks
from ione_core.dashboard_labels import localize_chart_config, localize_period_label


class TestDashboardLabels(TestCase):
	def test_education_home_dashboard_strings_are_localized(self):
		translations_path = Path(__file__).resolve().parents[1] / "translations" / "zh.csv"
		with translations_path.open(encoding="utf-8", newline="") as translations_file:
			translations = dict(csv.reader(translations_file))

		expected = {
			"Select Date Range": "选择日期范围",
			"Last Year": "过去一年",
			"Last Quarter": "过去一个季度",
			"Last Month": "过去一个月",
			"Last Week": "过去一周",
			"Yearly": "按年",
			"Quarterly": "按季度",
			"Monthly": "按月",
			"Weekly": "按周",
			"Daily": "按日",
			"No Data": "暂无数据",
			"just now": "刚刚",
			"Refresh": "刷新",
			"Edit": "编辑",
			"Export": "导出",
		}
		self.assertEqual({key: translations.get(key) for key in expected}, expected)

	def test_monthly_label_is_localized_for_chinese(self):
		self.assertEqual(localize_period_label("Jul 2026", "zh"), "2026年7月")

	def test_quarterly_label_is_localized_for_chinese(self):
		self.assertEqual(localize_period_label("Quarter 3 2026", "zh-CN"), "2026年第3季度")

	def test_non_chinese_label_is_unchanged(self):
		self.assertEqual(localize_period_label("Jul 2026", "en"), "Jul 2026")

	def test_chart_config_is_copied_before_localizing(self):
		config = {"labels": ["Jul 2025", "Jan 2026"], "datasets": [{"values": [1, 2]}]}

		localized = localize_chart_config(config, "zh")

		self.assertEqual(localized["labels"], ["2025年7月", "2026年1月"])
		self.assertEqual(config["labels"], ["Jul 2025", "Jan 2026"])
		self.assertIsNot(localized, config)

	def test_dashboard_chart_api_uses_localizing_wrapper(self):
		self.assertEqual(
			hooks.override_whitelisted_methods["frappe.desk.doctype.dashboard_chart.dashboard_chart.get"],
			"ione_core.dashboard.get_dashboard_chart",
		)
