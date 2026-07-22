import frappe

ROLES = (
	("I-ONE User", 1),
	("I-ONE Manager", 1),
	("I-ONE AI Operator", 1),
	("I-ONE Auditor", 1),
)


def ensure_roles():
	for role_name, desk_access in ROLES:
		if frappe.db.exists("Role", role_name):
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
			"status": "启用",
			"description": "负责跨应用信息查询、任务拆解和受控业务执行。",
			"model_provider": "OpenClaw",
			"model_name": "qwen",
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
	ensure_default_agent()
	ensure_default_onboarding_flow()
