"""Read-only Role views for the custom console with native read permissions."""

import frappe
from frappe.database.query import Engine

from ione_core.navigation import NavigationPolicy, require_staff

LIST_FIELDS = ("name", "role_name", "disabled", "desk_access", "modified")
DETAIL_FIELDS = (*LIST_FIELDS, "home_page", "restrict_to_domain", "two_factor_auth")
SORT_FIELDS = set(LIST_FIELDS)


class RoleReadQuery(Engine):
	def requires_owner_constraint(self, role_permissions):
		# Link selection must not relax owner-only document reading.
		return bool(role_permissions.get("read") and "read" in (role_permissions.get("if_owner") or {}))


def require_reader():
	require_staff()
	policy = NavigationPolicy()
	if not policy.administrator and not policy.allows("DocType", "Role"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


def integer(value, minimum, maximum):
	try:
		result = int(str(value))
	except ValueError, TypeError:
		frappe.throw(frappe._("Invalid pagination"), frappe.ValidationError)
	if not minimum <= result <= maximum:
		frappe.throw(frappe._("Invalid pagination"), frappe.ValidationError)
	return result


def present(row):
	from frappe.core.doctype.role.role import STANDARD_ROLES
	from frappe.permissions import AUTOMATIC_ROLES

	return {
		**row,
		"label": frappe._(row.get("role_name") or row["name"]),
		"is_reserved": row["name"] in {*STANDARD_ROLES, *AUTOMATIC_ROLES},
	}


def response(rows, total):
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {"data": [present(row) for row in rows], "total": total, "success": True}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_roles(
	current=1,
	page_size=20,
	keyword="",
	disabled=None,
	desk_access=None,
	sort_field="role_name",
	sort_order="ascend",
):
	require_reader()
	current = integer(current, 1, 1_000_000)
	page_size = integer(page_size, 1, 100)
	if sort_field not in SORT_FIELDS or sort_order not in ("ascend", "descend"):
		frappe.throw(frappe._("Invalid sort"), frappe.ValidationError)
	if (
		not isinstance(keyword, str)
		or len(keyword) > 120
		or disabled not in (None, "", 0, 1, "0", "1")
		or desk_access not in (None, "", 0, 1, "0", "1")
	):
		frappe.throw(frappe._("Invalid filters"), frappe.ValidationError)
	filters = {
		key: int(value)
		for key, value in {"disabled": disabled, "desk_access": desk_access}.items()
		if value not in (None, "")
	}
	query = {"table": "Role", "ignore_permissions": False, "db_query_compat": True}
	keyword = keyword.strip().casefold()
	if keyword:
		# Translate only names the caller can read. Literal matching also keeps % and
		# _ literal and supports Chinese labels without changing stored role IDs.
		candidates = (
			RoleReadQuery()
			.get_query(fields=["name", "role_name"], filters=filters, limit=None, **query)
			.run(as_dict=True)
		)
		matches = [
			row.name
			for row in candidates
			if any(
				keyword in str(value or "").casefold()
				for value in (row.name, row.get("role_name"), frappe._(row.get("role_name") or row.name))
			)
		]
		if not matches:
			return response([], 0)
		filters["name"] = ["in", matches]
	direction = "asc" if sort_order == "ascend" else "desc"
	rows = (
		RoleReadQuery()
		.get_query(
			fields=list(LIST_FIELDS),
			filters=filters,
			order_by=f"{sort_field} {direction}, name asc",
			offset=(current - 1) * page_size,
			limit=page_size,
			**query,
		)
		.run(as_dict=True)
	)
	counts = (
		RoleReadQuery()
		.get_query(
			fields=[{"COUNT": "name", "as": "total"}], filters=filters, limit=1, order_by=None, **query
		)
		.run(as_dict=True)
	)
	return response(rows, int(counts[0].total) if counts else 0)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_role(role):
	require_reader()
	if not isinstance(role, str) or not role or len(role) > 140:
		frappe.throw(frappe._("Invalid role"), frappe.ValidationError)
	doc = frappe.get_doc("Role", role)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	values = doc.as_dict()
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return present({key: values[key] for key in DETAIL_FIELDS if key in values})
