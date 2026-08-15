import sys
from types import ModuleType
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.audit import request_summary
from ione_core.mcp.tongjianyun_recipe import (
	DISH_DOCTYPE,
	INGREDIENT_DOCTYPE,
	RECIPE_DOCTYPE,
	upsert_tongjianyun_recipe,
	validate_recipe_payload,
)


def sample_recipe():
	return {
		"recipeId": "2026-W17",
		"title": "第十七周食谱",
		"weekStart": "2026-06-22",
		"weekEnd": "2026-06-26",
	}


def sample_days():
	return [
		{
			"id": "MON",
			"date": "2026-06-22",
			"day": "周一",
			"portions": [
				{
					"slot": "breakfast",
					"dishes": ["纯牛奶", "水煮鹌鹑蛋"],
					"dishIngredientRows": [
						{
							"dishName": "纯牛奶",
							"ingredient": "牛奶",
							"amount": 200,
							"unit": "g",
						}
					],
				}
			],
		}
	]


class FakeDB:
	def __init__(self):
		self.savepoints = []
		self.rollbacks = []

	def exists(self, doctype, filters):
		if doctype == RECIPE_DOCTYPE:
			return "2026-W17"
		return None

	def savepoint(self, name):
		self.savepoints.append(name)

	def rollback(self, *, save_point):
		self.rollbacks.append(save_point)

	def count(self, doctype, filters):
		return {DISH_DOCTYPE: 2, INGREDIENT_DOCTYPE: 1}[doctype]


class TestTongjianyunRecipeMCP(TestCase):
	def test_validates_and_counts_recipe_details(self):
		result = validate_recipe_payload(sample_recipe(), sample_days())
		self.assertEqual(result["dish_count"], 2)
		self.assertEqual(result["ingredient_count"], 1)

	def test_rejects_duplicate_meal_slots(self):
		days = sample_days()
		days[0]["portions"].append(dict(days[0]["portions"][0]))
		with self.assertRaisesRegex(ValueError, "duplicate meal slot"):
			validate_recipe_payload(sample_recipe(), days)

	def test_rejects_duplicate_day_ids(self):
		days = sample_days()
		days.append(dict(days[0]))
		with self.assertRaisesRegex(ValueError, "duplicate day id"):
			validate_recipe_payload(sample_recipe(), days)

	def test_upserts_with_permissions_and_verifies_generated_rows(self):
		db = FakeDB()
		frappe = ModuleType("frappe")
		frappe.db = db
		frappe.get_installed_apps = lambda: ["frappe", "tongjianyun"]

		storage = ModuleType("tongjianyun.recipe_storage")
		storage.save_recipe_payload = lambda payload, commit=False: {
			"recipe": payload["recipe"],
			"days": payload["days"],
		}
		package = ModuleType("tongjianyun")
		package.__path__ = []
		permissions = []

		with (
			patch.dict(
				sys.modules,
				{"frappe": frappe, "tongjianyun": package, "tongjianyun.recipe_storage": storage},
			),
			patch(
				"ione_core.mcp.tongjianyun_recipe.ensure_doctype_permission",
				side_effect=lambda doctype, permission: permissions.append((doctype, permission)),
			),
		):
			result = upsert_tongjianyun_recipe(sample_recipe(), sample_days())

		self.assertFalse(result["created"])
		self.assertEqual(result["name"], "2026-W17")
		self.assertEqual(result["dish_count"], 2)
		self.assertEqual(result["ingredient_count"], 1)
		self.assertEqual(db.savepoints, ["ione_mcp_tongjianyun_recipe"])
		self.assertEqual(db.rollbacks, [])
		self.assertEqual(
			permissions,
			[
				(RECIPE_DOCTYPE, "write"),
				(DISH_DOCTYPE, "create"),
				(DISH_DOCTYPE, "delete"),
				(INGREDIENT_DOCTYPE, "create"),
				(INGREDIENT_DOCTYPE, "delete"),
			],
		)

	def test_recipe_audit_summary_does_not_store_meal_content(self):
		result = request_summary({"recipe": sample_recipe(), "days": sample_days()})
		self.assertIn("2026-W17", result)
		self.assertIn('"count": 1', result)
		self.assertNotIn("纯牛奶", result)
		self.assertNotIn("第十七周食谱", result)
