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
			"now": "现在",
			"1 minute ago": "1 分钟前",
			"{0} minutes ago": "{0} 分钟前",
			"1 hour ago": "1 小时前",
			"{0} hours ago": "{0} 小时前",
			"yesterday": "昨天",
			"{0} days ago": "{0} 天前",
			"1 week ago": "1 周前",
			"{0} weeks ago": "{0} 周前",
			"1 month ago": "1 个月前",
			"{0} months ago": "{0} 个月前",
			"1 year ago": "1 年前",
			"{0} years ago": "{0} 年前",
			"{0} m": "{0} 分钟",
			"{0} h": "{0} 小时",
			"{0} d": "{0} 天",
			"{0} w": "{0} 周",
			"{0} M": "{0} 个月",
			"{0} y": "{0} 年",
			"Refresh": "刷新",
			"Edit": "编辑",
			"Export": "导出",
			"Loading...": "加载中...",
			"Equals": "等于",
			"Apply Filters": "应用筛选",
			"Date": "日期",
			"Timespan": "时间范围",
			"This Month": "本月",
			"ID": "编号",
			"New": "新建",
			"Like": "匹配",
			"In": "在...中",
			"Is": "是",
			"Between": "介于",
			"Last 7 Days": "最近 7 天",
			"Last 30 Days": "最近 30 天",
			"Last 90 Days": "最近 90 天",
			"Last 6 Months": "最近 6 个月",
			"Yesterday": "昨天",
			"Today": "今天",
			"Tomorrow": "明天",
			"This Week": "本周",
			"This Quarter": "本季度",
			"This Year": "今年",
			"Next Week": "下周",
			"Next Month": "下月",
			"Next Quarter": "下季度",
			"Next 6 Months": "未来 6 个月",
			"Next Year": "明年",
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
