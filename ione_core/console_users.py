"""Read-only User listing for the custom console, using native row/field permissions."""

import frappe
from frappe.database.query import Engine

from ione_core.navigation import NavigationPolicy, require_staff

FIELDS = ("name", "full_name", "username", "email", "enabled", "user_type", "modified")
SORT_FIELDS = set(FIELDS)


class UserReadQuery(Engine):
	def requires_owner_constraint(self, role_permissions):
		# Link selection can be unrestricted while reading records is owner-only.
		# Retain native user/share/field rules without letting select relax read.
		return bool(role_permissions.get("read") and "read" in (role_permissions.get("if_owner") or {}))


def integer(value, minimum, maximum):
	try:
		result = int(str(value))
	except ValueError, TypeError:
		frappe.throw(frappe._("Invalid pagination"), frappe.ValidationError)
	if not minimum <= result <= maximum:
		frappe.throw(frappe._("Invalid pagination"), frappe.ValidationError)
	return result


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_users(
	current=1,
	page_size=20,
	keyword="",
	enabled=None,
	user_type=None,
	sort_field="modified",
	sort_order="descend",
):
	require_staff()
	policy = NavigationPolicy()
	if not policy.administrator and not policy.allows("DocType", "User"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	current = integer(current, 1, 1_000_000)
	page_size = integer(page_size, 1, 100)
	if sort_field not in SORT_FIELDS or sort_order not in ("ascend", "descend"):
		frappe.throw(frappe._("Invalid sort"), frappe.ValidationError)
	keyword = str(keyword or "").strip()
	if (
		len(keyword) > 120
		or enabled not in (None, "", 0, 1, "0", "1")
		or user_type not in (None, "", "System User", "Website User")
	):
		frappe.throw(frappe._("Invalid filters"), frappe.ValidationError)
	filters = {}
	if enabled not in (None, ""):
		filters["enabled"] = int(enabled)
	if user_type:
		filters["user_type"] = user_type
	pattern = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	or_filters = (
		{field: ["like", pattern] for field in ("name", "full_name", "username", "email")} if keyword else {}
	)
	# Both rows and totals must use the identical native permission conditions. Do not
	# use get_all/db.count, which would expose records outside this user's data scope.
	query = {
		"table": "User",
		"filters": filters,
		"or_filters": or_filters,
		"ignore_permissions": False,
		"db_query_compat": True,
	}
	direction = "asc" if sort_order == "ascend" else "desc"
	rows = (
		UserReadQuery()
		.get_query(
			fields=list(FIELDS),
			order_by=f"{sort_field} {direction}, name asc",
			offset=(current - 1) * page_size,
			limit=page_size,
			**query,
		)
		.run(as_dict=True)
	)
	counts = (
		UserReadQuery()
		.get_query(fields=[{"COUNT": "name", "as": "total"}], order_by=None, limit=1, **query)
		.run(as_dict=True)
	)
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {"data": rows, "total": int(counts[0].total) if counts else 0, "success": True}
