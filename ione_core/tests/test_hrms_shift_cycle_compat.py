import ast
import copy
import datetime as dt
import functools
import hashlib
import importlib.util
import os
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIXIN_PATH = "ione_core.hrms_compat.shift_schedule_assignment.PreserveShiftCycleBoundaryMixin"
REFERENCE_DIRECTORY = os.environ.get("IONE_HRMS_COMPAT_REFERENCE_DIR")
REFERENCES = pathlib.Path(REFERENCE_DIRECTORY) if REFERENCE_DIRECTORY else None
REFERENCE_HASHES = {
	"reference-official-shift-schedule-assignment.py": "ad7d9b0781ef9cd253155a950d222ab617362c59d15da356206c654a34486bba",
	"reference-frappe-document.py": "8664241930e2c3f61836be0af97b7d518b04e41dbcce6f8f8965a2682032863a",
}


def reference_source(filename):
	"""Fail closed when the external official reference differs from the reviewed revision."""
	content = (REFERENCES / filename).read_bytes()
	if hashlib.sha256(content).hexdigest() != REFERENCE_HASHES[filename]:
		raise ValueError(f"Unexpected official source checksum: {filename}")
	return content.decode("utf-8")


def getdate(value):
	if isinstance(value, dt.datetime):
		return value.date()
	return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)


def add_days(value, days):
	result = getdate(value) + dt.timedelta(days=days)
	return result.isoformat() if isinstance(value, str) else result


STATE = types.SimpleNamespace(schedule=None, documents={}, failure_at=None, get_doc_error=None)
frappe = types.ModuleType("frappe")
utils = types.ModuleType("frappe.utils")
utils.getdate = getdate
frappe.utils = utils
frappe._dict = dict
frappe.bold = str
frappe.log_error = lambda error: STATE.errors.append(str(error))


def get_doc(doctype, name):
	if STATE.get_doc_error:
		raise STATE.get_doc_error
	if doctype == "Shift Schedule":
		return STATE.schedule
	if doctype == "Shift Schedule Assignment":
		return STATE.documents[name]
	raise AssertionError((doctype, name))


frappe.get_doc = get_doc
frappe.get_all = lambda *args, **kwargs: list(STATE.documents)
spec = importlib.util.spec_from_file_location(
	"candidate_shift_boundary", ROOT / "ione_core/hrms_compat/shift_schedule_assignment.py"
)
candidate = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
	spec.loader.exec_module(candidate)
Mixin = candidate.PreserveShiftCycleBoundaryMixin


class MemoryDocument:
	def __init__(self, name="isolated-assignment"):
		self.name = name
		self.employee = "test-employee"
		self.company = "test-company"
		self.shift_status = "Inactive"
		self.shift_location = "test-location"
		self.shift_schedule = "test-schedule"
		self.create_shifts_after = None
		self.rows = []
		self.cursor_writes = []
		self.comments = []
		self.raise_final_cursor = None
		STATE.documents[name] = self

	def db_set(self, field, value, **kwargs):
		if self.raise_final_cursor is not None and getdate(value) == self.raise_final_cursor:
			raise RuntimeError("simulated cursor persistence failure")
		self.cursor_writes.append((field, getdate(value), kwargs))
		setattr(self, field, value)

	def add_comment(self, **kwargs):
		self.comments.append(kwargs)


def create_shift_assignment(employee, company, shift_type, start, end, status, location, name):
	doc = STATE.documents[name]
	if STATE.failure_at == len(doc.rows) + 1:
		raise RuntimeError("simulated native assignment failure")
	doc.rows.append((employee, company, shift_type, getdate(start), getdate(end), status, location, name))


if REFERENCE_DIRECTORY:
	native_source = reference_source("reference-official-shift-schedule-assignment.py")
	native_tree = ast.parse(native_source)
	native_class_node = next(
		node
		for node in native_tree.body
		if isinstance(node, ast.ClassDef) and node.name == "ShiftScheduleAssignment"
	)
	native_scope = {
		"Document": MemoryDocument,
		"frappe": frappe,
		"getdate": getdate,
		"add_days": add_days,
		"get_weekday": lambda value: getdate(value).strftime("%A"),
		"create_shift_assignment": create_shift_assignment,
		"nowdate": lambda: "2026-10-22",
		"_": lambda value: value,
		"format_date": lambda value: str(value),
	}
	exec(
		compile(
			ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(native_class_node)], type_ignores=[])),
			str(REFERENCES / "reference-official-shift-schedule-assignment.py"),
			"exec",
		),
		native_scope,
	)
	Native = native_scope["ShiftScheduleAssignment"]

	legacy_node = copy.deepcopy(native_class_node)
	legacy_node.name = "LegacyPatchedShiftScheduleAssignment"
	legacy_method = next(
		node
		for node in legacy_node.body
		if isinstance(node, ast.FunctionDef) and node.name == "create_shifts"
	)
	legacy_method.body.extend(
		ast.parse('self.db_set("create_shifts_after", add_days(date, -1), update_modified=False)').body
	)
	exec(
		compile(
			ast.fix_missing_locations(ast.Module(body=[legacy_node], type_ignores=[])),
			"exact_existing_production_fix",
			"exec",
		),
		native_scope,
	)
	Legacy = native_scope["LegacyPatchedShiftScheduleAssignment"]
	scheduler_node = next(
		node
		for node in native_tree.body
		if isinstance(node, ast.FunctionDef) and node.name == "process_auto_shift_creation"
	)
	exec(
		compile(
			ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(scheduler_node)], type_ignores=[])),
			"official_scheduler",
			"exec",
		),
		native_scope,
	)

	framework_tree = ast.parse(reference_source("reference-frappe-document.py"))
	framework_names = {
		"_get_extended_class",
		"_create_extended_class",
		"_reduce_extended_instance",
		"_reconstruct_extended_instance",
	}
	framework_nodes = [
		copy.deepcopy(node)
		for node in framework_tree.body
		if isinstance(node, ast.FunctionDef) and node.name in framework_names
	]
	framework_scope = {"frappe": frappe, "functools": functools}
	exec(
		compile(
			ast.fix_missing_locations(ast.Module(body=framework_nodes, type_ignores=[])),
			"official_frappe_extension_loader",
			"exec",
		),
		framework_scope,
	)
	frappe.get_hooks = lambda *args, **kwargs: {"Shift Schedule Assignment": [MIXIN_PATH]}
	frappe.get_attr = lambda path: Mixin if path == MIXIN_PATH else None
	Extended = framework_scope["_get_extended_class"](Native, "Shift Schedule Assignment")


def set_schedule(weeks, days):
	STATE.schedule = types.SimpleNamespace(
		frequency="Every Week" if weeks == 1 else f"Every {weeks} Weeks",
		repeat_on_days=[types.SimpleNamespace(day=day) for day in days],
		shift_type="native-shift-type",
	)
	STATE.documents = {}
	STATE.failure_at = None
	STATE.get_doc_error = None
	STATE.errors = []


def dates_in_rows(rows):
	return [getdate(add_days(row[3], offset)) for row in rows for offset in range((row[4] - row[3]).days + 1)]


def fixed_origin_calendar(start, end, weeks, days):
	first = getdate(start)
	return [
		first + dt.timedelta(days=offset)
		for offset in range((getdate(end) - first).days + 1)
		if (offset // 7) % weeks == 0 and (first + dt.timedelta(days=offset)).strftime("%A") in days
	]


@unittest.skipUnless(
	REFERENCE_DIRECTORY,
	"Set IONE_HRMS_COMPAT_REFERENCE_DIR to pinned official sources; see docs/hrms-shift-cycle-compat.md.",
)
class ShiftCycleExtensionTests(unittest.TestCase):
	def test_original_24_two_batch_cases_use_fixed_origin_calendar(self):
		for weeks in [1, 2, 3, 4]:
			for start in ["2026-10-12", "2026-10-21"]:
				for days in [("Monday",), ("Wednesday",), ("Monday", "Friday")]:
					with self.subTest(weeks=weeks, start=start, days=days):
						set_schedule(weeks, days)
						doc = Extended()
						doc.create_shifts(start)
						doc.create_shifts(add_days(doc.create_shifts_after, 1))
						self.assertEqual(
							dates_in_rows(doc.rows),
							fixed_origin_calendar(start, doc.create_shifts_after, weeks, days),
						)

	def test_repeated_default_batches_never_shift_recurrence_anchor(self):
		for weeks in [1, 2, 3, 4]:
			with self.subTest(weeks=weeks):
				set_schedule(weeks, ("Monday", "Friday"))
				doc = Extended()
				start = "2027-12-29"
				next_start = start
				for _ in range(5):
					doc.create_shifts(next_start)
					next_start = add_days(doc.create_shifts_after, 1)
				self.assertEqual(
					dates_in_rows(doc.rows),
					fixed_origin_calendar(start, doc.create_shifts_after, weeks, ("Monday", "Friday")),
				)

	def test_explicit_horizons_preserve_every_native_assignment_boundary(self):
		for weeks in [1, 2, 3, 4]:
			for horizon in [-1, 0, 1, 5, 6, 7, 13, 14, 20, 21, 27, 28, 89, 90, 91, 97, 104, 111]:
				with self.subTest(weeks=weeks, horizon=horizon):
					set_schedule(weeks, ("Monday", "Tuesday", "Friday"))
					start, end = "2028-02-23", add_days("2028-02-23", horizon)
					native, legacy, extended = Native("native"), Legacy("legacy"), Extended("extended")
					for doc in [native, legacy, extended]:
						self.assertIsNone(doc.create_shifts(start, end))

					def without_identity(rows):
						return [row[:-1] for row in rows]

					self.assertEqual(without_identity(extended.rows), without_identity(native.rows))
					self.assertEqual(without_identity(extended.rows), without_identity(legacy.rows))
					self.assertEqual(
						getdate(extended.create_shifts_after), getdate(legacy.create_shifts_after)
					)
					self.assertEqual(extended.cursor_writes[-1][2], {"update_modified": False})

	def test_first_default_batch_is_identical_to_native_for_all_weekdays(self):
		for weeks in [1, 2, 3, 4]:
			set_schedule(
				weeks, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
			)
			native, extended = Native("native"), Extended("extended")
			native.create_shifts("2026-10-12")
			extended.create_shifts("2026-10-12")
			self.assertEqual([row[:-1] for row in native.rows], [row[:-1] for row in extended.rows])

	def test_no_repeat_days_still_advances_processed_window(self):
		for weeks in [1, 2, 3, 4]:
			set_schedule(weeks, ())
			doc, legacy = Extended("extended"), Legacy("legacy")
			doc.create_shifts("2026-10-12")
			legacy.create_shifts("2026-10-12")
			self.assertFalse(doc.rows)
			self.assertEqual(getdate(doc.create_shifts_after), getdate(legacy.create_shifts_after))

	def test_native_assignment_error_does_not_advance_final_boundary(self):
		set_schedule(3, ("Monday", "Friday"))
		native, extended = Native("native"), Extended("extended")
		STATE.failure_at = 2
		for doc in [native, extended]:
			with self.assertRaisesRegex(RuntimeError, "native assignment failure"):
				doc.create_shifts("2026-10-12")
		self.assertEqual(getdate(native.create_shifts_after), getdate(extended.create_shifts_after))
		self.assertEqual(native.cursor_writes, extended.cursor_writes)

	def test_schedule_lookup_error_has_no_cursor_write(self):
		set_schedule(3, ("Monday",))
		doc = Extended()
		STATE.get_doc_error = LookupError("schedule unavailable")
		with self.assertRaisesRegex(LookupError, "schedule unavailable"):
			doc.create_shifts("2026-10-12")
		self.assertFalse(doc.cursor_writes)
		self.assertFalse(doc.rows)

	def test_unsupported_frequency_keeps_native_error(self):
		set_schedule(3, ("Monday",))
		STATE.schedule.frequency = "unsupported"
		for controller in [Native, Extended]:
			doc = controller(controller.__name__)
			with self.assertRaises(KeyError):
				doc.create_shifts("2026-10-12")
			self.assertFalse(doc.cursor_writes)

	def test_cursor_persistence_error_propagates_without_commit(self):
		set_schedule(3, ("Monday",))
		doc = Extended()
		doc.raise_final_cursor = dt.date(2027, 1, 24)
		with self.assertRaisesRegex(RuntimeError, "cursor persistence failure"):
			doc.create_shifts("2026-10-12")
		self.assertEqual(getdate(doc.create_shifts_after), dt.date(2027, 1, 4))

	def test_official_scheduler_retrieves_extended_controller(self):
		set_schedule(3, ("Monday",))
		doc = Extended()
		doc.create_shifts_after = "2026-10-11"
		native_scope["process_auto_shift_creation"]()
		self.assertEqual(getdate(doc.create_shifts_after), dt.date(2027, 1, 24))
		self.assertEqual(len(doc.comments), 1)
		self.assertFalse(STATE.errors)

	def test_extension_loader_preserves_other_cooperative_mixins(self):
		class OtherMixin:
			def create_shifts(self, start_date, end_date=None):
				self.other_extension_called = True
				return super().create_shifts(start_date, end_date)

		set_schedule(3, ("Monday",))
		original_get_hooks, original_get_attr = frappe.get_hooks, frappe.get_attr
		try:
			frappe.get_hooks = lambda *args, **kwargs: {
				"Shift Schedule Assignment": [MIXIN_PATH, "other.Mixin"]
			}
			frappe.get_attr = lambda path: OtherMixin if path == "other.Mixin" else Mixin
			controller = framework_scope["_get_extended_class"](Native, "Shift Schedule Assignment")
			doc = controller()
			doc.create_shifts("2026-10-12")
			self.assertTrue(doc.other_extension_called)
			self.assertEqual(getdate(doc.create_shifts_after), dt.date(2027, 1, 24))
		finally:
			frappe.get_hooks, frappe.get_attr = original_get_hooks, original_get_attr


if __name__ == "__main__":
	unittest.main(verbosity=2)
