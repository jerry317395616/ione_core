import json
import unittest

from ione_core.setup.education_workspace import (
	CARD_GROUPS,
	DASHBOARD_CHART_SPECS,
	NUMBER_CARD_SPECS,
	SHORTCUT_SPECS,
	WORKSPACE_NAME,
	build_sidebar_items,
	build_workspace_content,
	build_workspace_links,
)


class EducationWorkspaceTest(unittest.TestCase):
	def test_sidebar_has_home_actions_and_collapsible_business_sections(self):
		items = build_sidebar_items()
		self.assertEqual(items[0]["label"], "主页")
		self.assertEqual(items[0]["link_type"], "Workspace")
		self.assertEqual(items[0]["link_to"], WORKSPACE_NAME)

		sections = [item for item in items if item["type"] == "Section Break"]
		self.assertEqual(
			[item["label"] for item in sections],
			["招生与学籍", "教学管理", "考勤与请假", "考核与成绩", "收费与财务", "基础设置"],
		)
		self.assertTrue(all(item["keep_closed"] for item in sections))
		self.assertTrue(all(item["child"] == 1 for item in items if not item["icon"]))

	def test_workspace_content_references_every_configured_component(self):
		content = json.loads(build_workspace_content())
		ids = [block["id"] for block in content]
		self.assertEqual(len(ids), len(set(ids)))

		card_names = {
			block["data"]["number_card_name"] for block in content if block["type"] == "number_card"
		}
		chart_names = {block["data"]["chart_name"] for block in content if block["type"] == "chart"}
		shortcut_names = {block["data"]["shortcut_name"] for block in content if block["type"] == "shortcut"}
		group_names = {block["data"]["card_name"] for block in content if block["type"] == "card"}

		self.assertEqual(card_names, {spec["name"] for spec in NUMBER_CARD_SPECS})
		self.assertEqual(chart_names, {spec["name"] for spec in DASHBOARD_CHART_SPECS})
		self.assertEqual(shortcut_names, {spec[0] for spec in SHORTCUT_SPECS})
		self.assertEqual(group_names, {group[0] for group in CARD_GROUPS})

	def test_workspace_link_cards_match_content_groups(self):
		links = build_workspace_links()
		breaks = [item for item in links if item["type"] == "Card Break"]
		self.assertEqual([item["label"] for item in breaks], [group[0] for group in CARD_GROUPS])
		self.assertEqual([item["link_count"] for item in breaks], [len(group[1]) for group in CARD_GROUPS])


if __name__ == "__main__":
	unittest.main()
