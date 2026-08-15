import csv
from pathlib import Path
from unittest import TestCase

from ione_core import hooks
from ione_core.dashboard_labels import localize_chart_config, localize_period_label


class TestDashboardLabels(TestCase):
	def test_education_home_dashboard_strings_are_localized(self):
		translations_path = Path(__file__).resolve().parents[1] / "translations" / "zh.csv"
		with translations_path.open(encoding="utf-8", newline="") as translations_file:
			rows = list(csv.reader(translations_file))
			translations = {row[0]: row[1] for row in rows if len(row) == 2}
			contextual_translations = {(row[0], row[2]): row[1] for row in rows if len(row) == 3}

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
			"List View": "列表视图",
			"Filter": "筛选",
			"Create": "新建",
			"First Name": "名字",
			"Import": "导入",
			"Customize Quick Filters": "自定义快速筛选",
			"New {0}": "新建{0}",
			"Not Saved": "未保存",
			"Templates": "模板",
			"Save": "保存",
			"Details": "基本信息",
			"Address": "地址",
			"Customer Details": "客户信息",
			"Exit": "离校",
			"Naming Series": "编号规则",
			"Middle Name": "中间名",
			"Last Name": "姓氏",
			"Personal Details": "个人信息",
			"Address Line 1": "地址第一行",
			"Address Line 2": "地址第二行",
			"City": "城市",
			"Country": "国家",
			"No.": "序号",
			"Full Name": "姓名",
			"Customer Group": "客户组",
			"Begin typing for results.": "输入内容以搜索。",
			"Batch": "批次",
			"Activity": "活动",
			"Instructors": "教师",
			"Schedule Date": "安排日期",
			"From Time": "开始时间",
			"To Time": "结束时间",
			"Based On": "依据",
			"Assessment Name": "考核名称",
			"Schedule": "日程安排",
			"Title": "标题",
			"Route": "路由",
			"Publish on website": "发布到网站",
			"Introduction": "简介",
			"Courses": "课程",
			"Course Name": "课程名称",
			"Table": "表格",
			"blue": "蓝色",
			"green": "绿色",
			"red": "红色",
			"orange": "橙色",
			"yellow": "黄色",
			"teal": "青绿色",
			"violet": "紫罗兰色",
			"cyan": "青色",
			"amber": "琥珀色",
			"pink": "粉色",
			"purple": "紫色",
			"Year Start Date": "学年开始日期",
			"Year End Date": "学年结束日期",
			"Name": "名称",
			"Content Type": "内容类型",
			"Content": "内容",
			"Description": "说明",
			"Employee": "员工",
			"Monday": "星期一",
			"Tuesday": "星期二",
			"Wednesday": "星期三",
			"Thursday": "星期四",
			"Friday": "星期五",
			"Saturday": "星期六",
			"Sunday": "星期日",
			"All Assessment Groups": "全部考核组",
			"Actions": "操作",
			"Assign To": "分配给",
			"Clear Assignment": "清除分配",
			"Delete": "删除",
			"Message": "消息",
			"Please set a default Holiday List for Company {0}": "请为公司 {0} 设置默认节假日列表",
			"Docstatus": "文档状态",
			"Assign": "分配",
			"Attachments": "附件",
			"Share": "分享",
			"Comments": "评论",
			"New Email": "新建邮件",
			"Attach": "上传",
			"Education Settings": "教育管理设置",
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
		self.assertEqual(translations["Guardian Interest"], "家长资源与参与意向")
		self.assertEqual(translations["Guardian Interests"], "家长资源与参与意向")
		self.assertEqual(contextual_translations[("Interests", "Guardian")], "可提供的资源与参与意向")
		self.assertEqual(
			contextual_translations[("Interest", "Guardian Interest")], "资源、特长或参与意向"
		)
		self.assertEqual(contextual_translations[("Type", "Student Log")], "类型")
		self.assertEqual(contextual_translations[("Log", "Student Log")], "日志内容")
		self.assertEqual(contextual_translations[("Result", "Assessment Result")], "考核结果")
		self.assertEqual(contextual_translations[("Summary", "Assessment Result")], "考核汇总")
		self.assertEqual(contextual_translations[("Comment", "Assessment Result")], "评语")
		self.assertEqual(contextual_translations[("Score", "Assessment Result Detail")], "得分")
		self.assertEqual(contextual_translations[("Grade", "Assessment Result Detail")], "等级")
		self.assertEqual(contextual_translations[("Amount", "Fee Component")], "金额")
		self.assertEqual(contextual_translations[("Total", "Fee Component")], "合计")
		self.assertEqual(contextual_translations[("Accounts", "Fee Structure")], "会计信息")
		self.assertEqual(
			contextual_translations[("Receivable Account", "Fee Structure")], "应收账款科目"
		)
		self.assertEqual(
			contextual_translations[("Accounting Dimensions", "Fee Structure")], "会计维度"
		)
		self.assertEqual(contextual_translations[("Cost Center", "Fee Structure")], "成本中心")
		self.assertEqual(
			contextual_translations[("Default Income Account", "Fee Category Default")],
			"默认收入科目",
		)
		self.assertEqual(
			contextual_translations[("Default Cost Center", "Fee Category Default")],
			"默认成本中心",
		)

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
