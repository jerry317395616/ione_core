import json
import unittest

from ione_core.setup.healthcare_workspace import (
	CARD_GROUPS,
	CHART_NAMES,
	NUMBER_CARD_NAMES,
	SHORTCUT_SPECS,
	SIDEBAR_WORKSPACES,
	WORKSPACE_SIDEBAR_SPECS,
	build_sidebar_items,
	build_workspace_content,
	build_workspace_links,
)


class HealthcareWorkspaceTest(unittest.TestCase):
	def test_every_primary_workspace_has_a_flat_secondary_menu(self):
		self.assertEqual(
			set(WORKSPACE_SIDEBAR_SPECS),
			{workspace for _label, workspace, _icon in SIDEBAR_WORKSPACES},
		)
		for workspace_name in WORKSPACE_SIDEBAR_SPECS:
			items = build_sidebar_items(workspace_name)
			self.assertEqual(items[0]["label"], "工作台")
			self.assertEqual(items[0]["link_type"], "Workspace")
			self.assertEqual(items[0]["link_to"], workspace_name)
			self.assertTrue(all(item["type"] == "Link" for item in items))
			self.assertTrue(all(item["child"] == 0 for item in items))

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

	def test_sidebar_targets_are_unique_within_each_workspace(self):
		for workspace_name in WORKSPACE_SIDEBAR_SPECS:
			items = build_sidebar_items(workspace_name)
			targets = [(item["link_type"], item["link_to"]) for item in items]
			self.assertEqual(len(targets), len(set(targets)))


if __name__ == "__main__":
	unittest.main()
