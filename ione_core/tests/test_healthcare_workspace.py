import json
import unittest

from ione_core.setup.healthcare_workspace import (
	CARD_GROUPS,
	CHART_NAMES,
	NUMBER_CARD_NAMES,
	SHORTCUT_SPECS,
	SIDEBAR_WORKSPACES,
	build_sidebar_items,
	build_workspace_content,
	build_workspace_links,
)


class HealthcareWorkspaceTest(unittest.TestCase):
	def test_sidebar_prioritizes_official_business_workspaces(self):
		items = build_sidebar_items()
		workspace_links = [item for item in items if item["link_type"] == "Workspace"]
		self.assertEqual(
			[(item["label"], item["link_to"]) for item in workspace_links],
			[(label, workspace) for label, workspace, _icon in SIDEBAR_WORKSPACES],
		)

		sections = [item for item in items if item["type"] == "Section Break"]
		self.assertEqual(
			[item["label"] for item in sections],
			["日常诊疗", "住院与护理", "检验与诊断", "康复管理", "医保与收费", "病历与报表", "机构与设置"],
		)
		self.assertTrue(all(item["keep_closed"] for item in sections))

	def test_workspace_content_references_every_configured_component(self):
		content = json.loads(build_workspace_content())
		ids = [block["id"] for block in content]
		self.assertEqual(len(ids), len(set(ids)))

		number_cards = {
			block["data"]["number_card_name"] for block in content if block["type"] == "number_card"
		}
		charts = {block["data"]["chart_name"] for block in content if block["type"] == "chart"}
		shortcuts = {block["data"]["shortcut_name"] for block in content if block["type"] == "shortcut"}
		groups = {block["data"]["card_name"] for block in content if block["type"] == "card"}

		self.assertEqual(number_cards, set(NUMBER_CARD_NAMES))
		self.assertEqual(charts, set(CHART_NAMES))
		self.assertEqual(shortcuts, {spec[0] for spec in SHORTCUT_SPECS})
		self.assertEqual(groups, {group[0] for group in CARD_GROUPS})

	def test_workspace_link_cards_match_content_groups(self):
		links = build_workspace_links()
		breaks = [item for item in links if item["type"] == "Card Break"]
		self.assertEqual([item["label"] for item in breaks], [group[0] for group in CARD_GROUPS])
		self.assertEqual([item["link_count"] for item in breaks], [len(group[1]) for group in CARD_GROUPS])

	def test_every_sidebar_child_is_grouped(self):
		items = build_sidebar_items()
		first_section = next(index for index, item in enumerate(items) if item["type"] == "Section Break")
		self.assertTrue(all(item["child"] == 1 for item in items[first_section:] if item["type"] == "Link"))


if __name__ == "__main__":
	unittest.main()
