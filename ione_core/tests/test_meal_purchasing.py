"""Offline authority/source/price tests; never create orders on a Frappe site."""

import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


class Doc:
	def __init__(self, **values):
		self.__dict__.update(values)
		self.flags = types.SimpleNamespace()
		self.check_permission = Mock()
		self.get_doc_before_save = Mock(return_value=None)
		self.reload = Mock()
		self.save = Mock()
		self.insert = Mock()
		self.db_set = Mock(side_effect=lambda field, value, **kwargs: setattr(self, field, value))
		self.add_comment = Mock()

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def set(self, key, value):
		setattr(self, key, value)


class MealPurchasingTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe.whitelist = lambda *args, **kwargs: lambda function: function
		self.frappe.PermissionError = PermissionError
		self.frappe.throw = Mock(
			side_effect=lambda message, *args: (_ for _ in ()).throw(ValueError(message))
		)
		self.frappe.db = Mock()
		self.frappe.db.sql.return_value = []
		self.frappe.db.exists.return_value = False
		self.stored_owners = {
			("Material Request", "MR"): "buyer@example.test",
			("Purchase Order", "PO"): "buyer@example.test",
			("Supplier Quotation", "SQ"): "buyer@example.test",
		}
		self.frappe.db.get_value.side_effect = lambda dt, name, field, **kwargs: self.stored_owners.get(
			(dt, name)
		)
		self.frappe.session = Doc(user="buyer@example.test")
		self.frappe.get_roles = Mock(return_value=["Purchase Manager"])
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.get_all = Mock(return_value=["PP"])
		self.frappe.as_json = json.dumps
		self.frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		self.addCleanup(self.modules.stop)
		folder = Path(__file__).parents[1]
		spec = importlib.util.spec_from_file_location(
			"ione_core.meal_procurement", folder / "meal_procurement.py"
		)
		procurement = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(procurement)
		self.extra = patch.dict(sys.modules, {"ione_core.meal_procurement": procurement})
		self.extra.start()
		self.addCleanup(self.extra.stop)
		spec = importlib.util.spec_from_file_location("tested_meal_purchasing", folder / "meal_purchasing.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.date_patch = patch.object(self.module, "_today", return_value=date(2026, 10, 23))
		self.date_patch.start()
		self.addCleanup(self.date_patch.stop)
		self.now_patch = patch.object(self.module, "_now", return_value="2026-10-23 12:00:00")
		self.now_patch.start()
		self.addCleanup(self.now_patch.stop)
		self.weight = patch.object(
			self.module, "_weight_proof", return_value={"confirmed": True, "basis": "采购毛重"}
		)
		self.weight.start()
		self.addCleanup(self.weight.stop)
		self.source = Doc(
			name="SOURCE",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			uom="g",
			quantity=50,
			conversion_factor=1,
		)
		self.plan = Doc(
			name="PP",
			company="园",
			custom_meal_week="WEEK",
			docstatus=1,
			status="Open",
			mr_items=[self.source],
		)
		self.mr_item = Doc(
			name="MRI",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			production_plan="PP",
			material_request_plan_item="SOURCE",
			qty=50,
			stock_qty=50,
			uom="g",
			stock_uom="g",
			conversion_factor=1,
			ordered_qty=0,
			received_qty=0,
		)
		self.mr = Doc(
			name="MR",
			company="园",
			owner="buyer@example.test",
			docstatus=1,
			status="Pending",
			material_request_type="Purchase",
			items=[self.mr_item],
		)
		self.week = Doc(name="WEEK", company="园", docstatus=1, material_request="MR")
		self.po_item = Doc(
			name="POI",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			material_request="MR",
			material_request_item="MRI",
			qty=50,
			stock_uom="g",
			uom="g",
			conversion_factor=1,
			rate=2.5,
			price_list_rate=2.5,
			discount_percentage=0,
			discount_amount=0,
			supplier_quotation="SQ",
			supplier_quotation_item="SQI",
		)
		self.po = Doc(
			name="PO",
			owner="buyer@example.test",
			company="园",
			supplier="SUPPLIER",
			currency="CNY",
			conversion_rate=1,
			transaction_date="2026-10-23",
			docstatus=0,
			items=[self.po_item],
			custom_meal_week="WEEK",
			custom_meal_quote_snapshot=None,
		)
		self.quote_item = Doc(
			name="SQI",
			item_code="rice",
			uom="g",
			stock_uom="g",
			conversion_factor=1,
			rate=2.5,
			price_list_rate=2.5,
			discount_percentage=0,
			discount_amount=0,
		)
		self.quote = Doc(
			name="SQ",
			owner="buyer@example.test",
			company="园",
			supplier="SUPPLIER",
			currency="CNY",
			transaction_date="2026-10-23",
			valid_till="2026-11-01",
			docstatus=1,
			items=[self.quote_item],
		)
		self.item = Doc(name="rice", item_name="Rice", stock_uom="g", uoms=[])
		self.documents = {
			("Material Request", "MR"): self.mr,
			("Production Plan", "PP"): self.plan,
			("Meal Planning Week", "WEEK"): self.week,
			("Purchase Order", "PO"): self.po,
			("Supplier Quotation", "SQ"): self.quote,
		}
		self.frappe.get_doc = Mock(
			side_effect=lambda doctype, name, **kwargs: self.documents[(doctype, name)]
		)
		self.frappe.get_cached_doc = Mock(
			side_effect=lambda doctype, name: self.item if doctype == "Item" else Doc(enabled=1, disabled=0)
		)

	def reviewed(self):
		week, sources = self.module._scope(self.po)
		basis = self.module._quote_basis(self.po, week, sources)
		self.po.custom_meal_quote_snapshot = json.dumps(
			{
				"confirmed": True,
				"confirmed_by": "reviewer@example.test",
				"basis_hash": self.module._hash(basis),
			}
		)

	def mr_fact(self, **values):
		fact = dict(
			name="MR",
			company="园",
			docstatus=1,
			status="Ordered",
			material_request_type="Purchase",
			source_item="MRI",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			stock_qty=50,
			ordered_qty=50,
			received_qty=0,
			production_plan="PP",
			material_request_plan_item="SOURCE",
			source_parent="PP",
			source_item_code="rice",
			source_warehouse="Stores",
		)
		fact.update(values)
		return Doc(**fact)

	def po_fact(self, **values):
		fact = dict(
			name="PO",
			company="园",
			docstatus=1,
			status="To Bill",
			source_item="POI",
			item_code="rice",
			warehouse="Stores",
			qty=50,
			received_qty=50,
			conversion_factor=1,
			material_request="MR",
			material_request_item="MRI",
			closed=0,
		)
		fact.update(values)
		return Doc(**fact)

	def test_unrelated_native_order_passes_through(self):
		doc = Doc(items=[], docstatus=0)
		self.module.validate_purchase_order(doc)
		self.module.before_submit_purchase_order(doc)

	def test_week_label_without_native_sources_is_rejected(self):
		self.po.items = []
		with self.assertRaisesRegex(ValueError, "label alone"):
			self.module._scope(self.po)

	def test_native_source_item_mismatch_is_rejected(self):
		self.source.item_code = "OTHER"
		with self.assertRaisesRegex(ValueError, "native Production Plan"):
			self.module._scope(self.po)

	def test_mixed_sources_are_not_accepted_as_a_meal_order(self):
		self.po.items.append(Doc(item_code="other", material_request=None, material_request_item=None))
		with self.assertRaisesRegex(ValueError, "only approved native sources"):
			self.module._scope(self.po)

	def test_existing_price_list_alone_is_not_a_supplier_quotation(self):
		self.po_item.supplier_quotation = None
		with self.assertRaisesRegex(ValueError, "actual submitted Supplier Quotation"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_zero_prices_cannot_be_confirmed_or_submitted(self):
		self.po_item.rate = 0
		with self.assertRaisesRegex(ValueError, "positive price"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_full_discount_cannot_hide_a_zero_effective_purchase_price(self):
		self.po_item.net_rate = 0
		with self.assertRaisesRegex(ValueError, "effective unit price"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_equal_numeric_conversion_values_do_not_look_like_source_tampering(self):
		self.assertTrue(self.module._same_source_value("conversion_factor", 1, 1.0))
		self.assertTrue(self.module._same_source_value("schedule_date", date(2026, 10, 26), "2026-10-26"))

	def test_foreign_currency_quotation_is_rejected(self):
		self.quote.currency = "USD"
		with self.assertRaisesRegex(ValueError, "currency"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_expired_quotation_is_rejected(self):
		self.quote.valid_till = "2026-10-22"
		with self.assertRaisesRegex(ValueError, "unexpired"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_unverified_unit_conversion_is_rejected(self):
		self.po_item.conversion_factor = 1000
		with self.assertRaisesRegex(ValueError, "unit conversion"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_price_changed_from_real_quotation_is_rejected(self):
		self.po_item.rate = 3
		with self.assertRaisesRegex(ValueError, "differs from"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_creator_cannot_confirm_own_quote_even_as_administrator(self):
		self.po.owner = self.frappe.session.user = "Administrator"
		self.frappe.get_roles.return_value = ["System Manager"]
		with self.assertRaisesRegex(ValueError, "administrators cannot self-approve"):
			self.module.confirm_purchase_order_quote("PO")
		self.po.save.assert_not_called()

	def test_second_reviewer_freezes_actual_quotation_without_submitting(self):
		self.frappe.session.user = "reviewer@example.test"
		result = self.module.confirm_purchase_order_quote("PO")
		snapshot = json.loads(self.po.custom_meal_quote_snapshot)
		self.assertTrue(result["confirmed"])
		self.assertEqual(snapshot["confirmed_by"], "reviewer@example.test")
		self.assertEqual(snapshot["quotation_names"], ["SQ"])
		self.assertEqual(self.po.docstatus, 0)
		self.po.save.assert_called_once_with()
		self.frappe.db.commit.assert_not_called()

	def test_stale_quote_confirmation_blocks_native_submit(self):
		self.reviewed()
		self.po_item.qty = 49
		with self.assertRaisesRegex(ValueError, "second purchaser"):
			self.module.before_submit_purchase_order(self.po)

	def test_orders_cannot_exceed_the_approved_request_even_after_quote_review(self):
		self.po_item.qty = 51
		with self.assertRaisesRegex(ValueError, "exceed the approved"):
			self.module._quote_basis(self.po, *self.module._scope(self.po))

	def test_valid_second_person_review_allows_native_submit_validation(self):
		self.reviewed()
		self.module.before_submit_purchase_order(self.po)

	def test_readonly_quote_snapshot_cannot_be_forged(self):
		self.po.get_doc_before_save.return_value = Doc(
			custom_meal_week="WEEK", custom_meal_quote_snapshot=None
		)
		self.po.custom_meal_quote_snapshot = "forged"
		with self.assertRaisesRegex(ValueError, "controlled actions"):
			self.module.validate_purchase_order(self.po)

	def test_narrow_business_operator_can_prepare_but_cannot_review_quotes(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		self.module._operator()
		with self.assertRaisesRegex(ValueError, "Purchase Manager"):
			self.module._manager()

	def test_narrow_business_operator_cannot_use_native_forms_to_edit_unrelated_requests(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		doc = Doc(name="UNRELATED", docstatus=0, material_request_type="Purchase", items=[])
		with self.assertRaisesRegex(ValueError, "verified meal material requests"):
			self.module.validate_material_request(doc)

	def test_narrow_business_operator_cannot_use_native_forms_to_edit_unrelated_orders(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		doc = Doc(name="UNRELATED", docstatus=0, items=[])
		with self.assertRaisesRegex(ValueError, "verified meal purchase orders"):
			self.module.validate_purchase_order(doc)

	def test_apply_actual_quote_saves_only_the_draft_and_clears_old_confirmation(self):
		self.po.custom_meal_quote_snapshot = "old"
		result = self.module.apply_supplier_quotation("PO", "SQ")
		self.assertTrue(result["needs_confirmation"])
		self.assertIsNone(self.po.custom_meal_quote_snapshot)
		self.assertEqual(self.po_item.rate, 2.5)
		self.po.save.assert_called_once_with()

	def test_material_request_cannot_exceed_its_frozen_source(self):
		self.mr.docstatus = 0
		self.mr_item.qty = self.mr_item.stock_qty = 51
		with self.assertRaisesRegex(ValueError, "exceed frozen"):
			self.module.validate_material_request(self.mr)

	def test_other_draft_request_already_uses_the_same_frozen_source_cap(self):
		self.mr.docstatus = 0
		other = Doc(name="OTHER-MR", company="园", owner="other@example.test", docstatus=0)
		self.documents[("Material Request", "OTHER-MR")] = other
		self.frappe.db.sql.return_value = [
			Doc(name="OTHER-MR", material_request_plan_item="SOURCE", allocated_qty=1)
		]
		with self.assertRaisesRegex(ValueError, "exceed frozen"):
			self.module.validate_material_request(self.mr)

	def test_material_request_date_must_match_frozen_requirement(self):
		self.mr_item.schedule_date = "2026-10-27"
		with self.assertRaisesRegex(ValueError, "frozen requirement date"):
			self.module.validate_material_request(self.mr)

	def test_original_material_request_sources_cannot_be_cleared(self):
		old = Doc(
			name="MR",
			company="园",
			owner=self.mr.owner,
			material_request_type="Purchase",
			items=[self.mr_item],
		)
		self.mr.get_doc_before_save.return_value = old
		self.mr.items = [Doc(item_code="rice")]
		with self.assertRaisesRegex(ValueError, "detached"):
			self.module.validate_material_request(self.mr)

	def test_material_request_creator_cannot_self_approve(self):
		with self.assertRaisesRegex(ValueError, "administrators cannot self-approve"):
			self.module.before_submit_material_request(self.mr)

	def test_meal_request_cannot_change_creator_by_ordinary_save(self):
		self.mr.get_doc_before_save.return_value = Doc(owner=self.mr.owner, items=[self.mr_item])
		self.mr.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.validate_material_request(self.mr)

	def test_meal_order_cannot_change_creator_even_in_managed_save(self):
		self.po.get_doc_before_save.return_value = Doc(
			owner=self.po.owner, custom_meal_week="WEEK", items=[self.po_item], company="园"
		)
		self.po.owner = "someone@example.test"
		with self.module._managed(), self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.validate_purchase_order(self.po)

	def test_request_submit_compares_creator_with_database(self):
		self.mr.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.before_submit_material_request(self.mr)
		self.frappe.db.get_value.assert_called_with("Material Request", "MR", "owner", for_update=True)

	def test_order_submit_compares_creator_with_database(self):
		self.reviewed()
		self.po.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.before_submit_purchase_order(self.po)
		self.frappe.db.get_value.assert_called_with("Purchase Order", "PO", "owner", for_update=True)

	def test_order_quote_confirmation_rechecks_database_creator_after_reload(self):
		self.frappe.session.user = "reviewer@example.test"
		self.stored_owners[("Purchase Order", "PO")] = "different@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.confirm_purchase_order_quote("PO")
		self.po.reload.assert_called_once()
		self.po.save.assert_not_called()

	def test_meal_operator_quotation_original_creator_cannot_be_rewritten_by_admin(self):
		self.frappe.session.user = "Administrator"
		self.frappe.get_roles.side_effect = lambda user=None: (
			["膳食业务经办员"] if user == "buyer@example.test" else ["System Manager"]
		)
		self.quote.get_doc_before_save.return_value = Doc(owner="buyer@example.test")
		self.quote.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.validate_supplier_quotation(self.quote)

	def test_new_meal_operator_quotation_cannot_impersonate_another_creator(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		self.quote.is_new = lambda: True
		self.quote.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "当前实际经办人"):
			self.module.validate_supplier_quotation(self.quote)

	def test_meal_operator_quotation_submit_rechecks_persisted_creator(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		self.quote.owner = "someone@example.test"
		with self.assertRaisesRegex(ValueError, "创建人不能修改"):
			self.module.validate_supplier_quotation(self.quote, "before_submit")
		self.frappe.db.get_value.assert_called_with("Supplier Quotation", "SQ", "owner", for_update=True)

	def test_unrelated_supplier_quotation_permissions_are_unchanged(self):
		self.quote.get_doc_before_save.return_value = Doc(owner="other@example.test")
		self.quote.owner = "another@example.test"
		self.module.validate_supplier_quotation(self.quote)
		self.frappe.db.get_value.assert_not_called()

	def test_administrator_inherits_all_roles_without_scoping_all_quotations(self):
		self.frappe.session.user = "Administrator"
		self.quote.get_doc_before_save.return_value = Doc(owner="other@example.test")
		self.quote.owner = "another@example.test"
		self.frappe.get_roles.side_effect = lambda user=None: (
			["膳食业务经办员", "System Manager"] if user == "Administrator" else ["Purchase User"]
		)
		self.module.validate_supplier_quotation(self.quote)
		self.frappe.db.get_value.assert_not_called()

	def test_supersession_requires_reciprocal_identical_native_sources(self):
		self.mr.docstatus = 0
		self.mr.custom_meal_superseded_by = "NEW"
		new = Doc(
			name="NEW",
			company="园",
			material_request_type="Purchase",
			owner="other@example.test",
			docstatus=0,
			custom_meal_replaces="MR",
			items=[self.mr_item],
		)
		self.documents[("Material Request", "NEW")] = new
		self.assertTrue(self.module.is_verified_superseded_request(self.mr))
		new.custom_meal_replaces = "WRONG"
		with self.assertRaisesRegex(ValueError, "verified identical replacement"):
			self.module.is_verified_superseded_request(self.mr)

	def test_a_superseded_original_cannot_be_submitted(self):
		self.mr.custom_meal_superseded_by = "NEW"
		with self.assertRaisesRegex(ValueError, "cannot be submitted"):
			self.module.before_submit_material_request(self.mr)

	def test_reissue_preserves_old_creator_and_records_current_actual_creator(self):
		self.mr.docstatus = 0
		self.mr.owner = "Administrator"
		new = Doc(
			name=None,
			company="园",
			material_request_type="Purchase",
			owner=None,
			docstatus=0,
			items=[self.mr_item],
		)
		self.frappe.copy_doc = Mock(return_value=new)
		naming = types.ModuleType("frappe.model.naming")
		naming.set_new_name = lambda doc: setattr(doc, "name", "NEW")
		with patch.dict(sys.modules, {"frappe.model.naming": naming}):
			result = self.module.reissue_material_request_draft("WEEK")
		self.assertEqual(result["material_request"], "NEW")
		self.assertEqual(self.mr.owner, "Administrator")
		self.assertEqual(new.owner, "buyer@example.test")
		self.assertEqual(self.mr.custom_meal_superseded_by, "NEW")
		self.assertEqual(new.custom_meal_replaces, "MR")
		self.assertEqual(self.week.material_request, "NEW")
		self.mr.add_comment.assert_called_once()
		new.add_comment.assert_called_once()
		new.insert.assert_called_once_with(set_name="NEW")

	def test_reissue_does_not_touch_a_request_with_downstream_orders(self):
		self.mr.docstatus = 0
		self.mr.owner = "Administrator"
		self.frappe.db.exists.return_value = True
		with self.assertRaisesRegex(ValueError, "downstream"):
			self.module.reissue_material_request_draft("WEEK")
		self.mr.db_set.assert_not_called()

	def test_week_settlement_blocks_unprocessed_material_request_draft(self):
		self.mr.docstatus = 0
		self.frappe.db.sql.side_effect = [[Doc(name="PP")], [self.mr_fact(docstatus=0)], []]
		with self.assertRaisesRegex(ValueError, "Draft material request"):
			self.module.verify_week_procurement_settled(self.week)

	def test_order_caps_use_current_rows_instead_of_old_transaction_snapshot(self):
		other = Doc(
			material_request_item="MRI",
			qty=1,
			received_qty=0,
			conversion_factor=1,
			closed=0,
			docstatus=0,
			status="Draft",
		)
		self.frappe.db.sql.side_effect = lambda query, *args, **kwargs: (
			[other] if "FOR UPDATE" in query else []
		)
		with self.assertRaisesRegex(ValueError, "exceed the approved"):
			self.module._validate_order_caps(self.po, self.module._scope(self.po)[1])

	def test_request_caps_use_current_rows_instead_of_old_transaction_snapshot(self):
		other = Doc(name="OTHER-MR", company="园", owner="other@example.test", docstatus=0)
		self.documents[("Material Request", "OTHER-MR")] = other
		allocated = Doc(name="OTHER-MR", material_request_plan_item="SOURCE", allocated_qty=1)
		self.frappe.db.sql.side_effect = lambda query, *args, **kwargs: (
			[allocated] if "allocated_qty" in query and "FOR UPDATE" in query else []
		)
		with self.assertRaisesRegex(ValueError, "exceed frozen"):
			self.module.validate_material_request(self.mr)

	def test_existing_draft_order_is_found_by_current_read_after_waiting_for_week_lock(self):
		self.documents[("Supplier", "SUPPLIER")] = Doc(disabled=0)

		def current_rows(query, *args, **kwargs):
			if "FOR UPDATE" not in query:
				return []
			if "FROM `tabProduction Plan`" in query:
				return [Doc(name="PP")]
			if "WHERE p.docstatus=0" in query:
				return [Doc(name="PO", supplier="SUPPLIER", material_request_item="MRI")]
			return []

		self.frappe.db.sql.side_effect = current_rows
		result = self.module.create_purchase_order_draft("WEEK", "SUPPLIER")
		self.assertEqual(result, {"purchase_order": "PO", "created": False})
		self.po.insert.assert_not_called()
		self.frappe.get_doc.assert_any_call("Material Request", "MR", for_update=True)

	def test_native_order_source_is_revalidated_with_current_read_after_week_lock(self):
		cancelled = Doc(**{key: value for key, value in self.mr.__dict__.items() if not key.startswith("_")})
		cancelled.docstatus = 2
		self.frappe.get_doc.side_effect = lambda dt, name, **kwargs: (
			cancelled if dt == "Material Request" and kwargs.get("for_update") else self.documents[(dt, name)]
		)
		with self.assertRaisesRegex(ValueError, "approved native sources"):
			self.module._scope(self.po, for_update=True)

	def test_week_settlement_blocks_unreceived_order(self):
		self.frappe.db.sql.side_effect = [
			[Doc(name="PP")],
			[self.mr_fact()],
			[self.po_fact(received_qty=49)],
			[],
		]
		with self.assertRaisesRegex(ValueError, "unreceived"):
			self.module.verify_week_procurement_settled(self.week)

	def test_week_settlement_blocks_receipt_drafts_even_after_other_receipts(self):
		receipt = Doc(name="PR", docstatus=0, stock_qty=1)
		self.frappe.db.sql.side_effect = [[Doc(name="PP")], [self.mr_fact()], [self.po_fact()], [receipt]]
		with self.assertRaisesRegex(ValueError, "Draft purchase receipt"):
			self.module.verify_week_procurement_settled(self.week)

	def test_week_settlement_keeps_manual_closure_remainder_in_proof(self):
		self.frappe.db.sql.side_effect = [
			[Doc(name="PP")],
			[self.mr_fact(status="Stopped", ordered_qty=0)],
			[self.po_fact(status="Closed", received_qty=0)],
			[],
		]
		proof = self.module.verify_week_procurement_settled(self.week)
		self.assertTrue(proof["settled"])
		self.assertEqual(len(proof["manually_closed_sources"]), 2)
		self.assertEqual(proof["purchase_orders"][0]["remaining_stock_qty"], "50")
		self.assertTrue(all("FOR UPDATE" in call.args[0] for call in self.frappe.db.sql.call_args_list))


if __name__ == "__main__":
	unittest.main()
