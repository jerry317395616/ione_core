import frappe

ROLES = (
	("I-ONE User", 1),
	("I-ONE Manager", 1),
	("I-ONE AI Operator", 1),
	("I-ONE Auditor", 1),
	("I-ONE AI Employee", 1),
)


def ensure_roles():
	for role_name, desk_access in ROLES:
		if frappe.db.exists("Role", role_name):
			if frappe.db.get_value("Role", role_name, "desk_access") != desk_access:
				frappe.db.set_value("Role", role_name, "desk_access", desk_access, update_modified=False)
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": desk_access,
				"is_custom": 0,
			}
		).insert(ignore_permissions=True)


def ensure_default_agent():
	if not frappe.db.exists("DocType", "I-ONE Agent"):
		return
	if frappe.db.exists("I-ONE Agent", {"agent_code": "ione-general"}):
		return

	frappe.get_doc(
		{
			"doctype": "I-ONE Agent",
			"agent_code": "ione-general",
			"agent_name": "I-ONE 通用助理",
			"agent_type": "综合助理",
			"status": "草稿",
			"description": "负责跨应用信息查询、任务拆解和受控业务执行。",
			"responsibilities": "负责跨应用信息查询、任务拆解和受控业务执行。",
			"operating_mode": "辅助",
			"allowed_modules": "ERPNext\nCRM\nHR\nHelpdesk\nDrive\nLearning\nGameplan\nInsights",
		}
	).insert(ignore_permissions=True)


def ensure_default_onboarding_flow():
	if not frappe.db.exists("DocType", "I-ONE Onboarding Flow"):
		return
	if frappe.db.exists("I-ONE Onboarding Flow", "mobile-default"):
		return

	from ione_core.onboarding_defaults import get_default_onboarding_flow_data

	frappe.get_doc(get_default_onboarding_flow_data()).insert(ignore_permissions=True)


def before_install():
	ensure_roles()


def after_install():
	ensure_roles()
	ensure_default_agent()
	ensure_default_onboarding_flow()


def after_migrate():
	ensure_roles()
	migrate_agent_fields()
	ensure_default_agent()
	ensure_default_onboarding_flow()
	ensure_runtime_config()


def ensure_runtime_config():
	from ione_core.runtime_config import ensure_web_request_timeout

	ensure_web_request_timeout()


def migrate_agent_fields():
	if not frappe.db.exists("DocType", "I-ONE Agent"):
		return
	frappe.db.sql(
		"""
		update `tabI-ONE Agent`
		set status = case
			when status = '启用' then '在职'
			when status = '停用' then '离职'
			else coalesce(nullif(status, ''), '草稿')
		end
		"""
	)
	default_model = None
	if "flow" in frappe.get_installed_apps() and frappe.db.exists("DocType", "Flow Model"):
		default_model = frappe.db.get_value(
			"Flow Model",
			{"enabled": 1},
			"name",
			order_by="creation asc",
		)
	if default_model:
		frappe.db.sql(
			"""
			update `tabI-ONE Agent`
			set flow_model = %s
			where ifnull(flow_model, '') = ''
			""",
			default_model,
		)
