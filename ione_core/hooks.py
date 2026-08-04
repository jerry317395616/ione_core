app_name = "ione_core"
app_title = "I-ONE AI"
app_publisher = "I-ONE"
app_description = "I-ONE AI unified Frappe service core"
app_email = "317395616@qq.com"
app_license = "mit"

app_home = "/desk/i-one-ai"
app_logo_url = "/assets/ione_core/images/ione-logo.svg"

app_include_js = ["/assets/ione_core/js/workspace_dock_i18n.js?v=20260804-1"]

add_to_apps_screen = [
	{
		"name": app_name,
		"title": app_title,
		"route": app_home,
		"logo": app_logo_url,
		"has_permission": "ione_core.api.has_app_permission",
	}
]

before_install = "ione_core.setup.install.before_install"
after_install = "ione_core.setup.install.after_install"
after_migrate = "ione_core.setup.install.after_migrate"

fixtures = [
	{"dt": "Role", "filters": [["role_name", "like", "I-ONE %"]]},
]

permission_query_conditions = {
	"I-ONE Smart Record": "ione_core.permissions.owner_query",
	"I-ONE AI Task": "ione_core.permissions.owner_query",
	"I-ONE AI Run Log": "ione_core.permissions.owner_query",
	"I-ONE Approval Request": "ione_core.permissions.approval_query",
	"I-ONE Growth Plan": "ione_core.permissions.owner_user_query",
	"I-ONE Evidence": "ione_core.permissions.owner_query",
	"I-ONE Experience": "ione_core.permissions.experience_query",
	"I-ONE Publish Job": "ione_core.permissions.owner_query",
	"I-ONE Evaluation": "ione_core.permissions.owner_query",
	"I-ONE Achievement": "ione_core.permissions.achievement_query",
	"I-ONE Expert Conversation": "ione_core.permissions.owner_user_query",
	"I-ONE Expert Message": "ione_core.permissions.owner_query",
	"I-ONE Onboarding Record": "ione_core.permissions.user_query",
}

has_permission = {
	"I-ONE Smart Record": "ione_core.permissions.owner_permission",
	"I-ONE AI Task": "ione_core.permissions.owner_permission",
	"I-ONE AI Run Log": "ione_core.permissions.owner_permission",
	"I-ONE Approval Request": "ione_core.permissions.approval_permission",
	"I-ONE Growth Plan": "ione_core.permissions.owner_user_permission",
	"I-ONE Evidence": "ione_core.permissions.owner_permission",
	"I-ONE Experience": "ione_core.permissions.experience_permission",
	"I-ONE Publish Job": "ione_core.permissions.owner_permission",
	"I-ONE Evaluation": "ione_core.permissions.owner_permission",
	"I-ONE Achievement": "ione_core.permissions.achievement_permission",
	"I-ONE Expert Conversation": "ione_core.permissions.owner_user_permission",
	"I-ONE Expert Message": "ione_core.permissions.owner_permission",
	"I-ONE Onboarding Record": "ione_core.permissions.user_permission",
}

doc_events = {
	"Flow Run": {
		"on_update": "ione_core.ai.sync_task_from_flow_run",
	},
}

override_whitelisted_methods = {
	"flow.api.start_run": "ione_core.flow_policy.start_run",
	"flow.api.api.start_run": "ione_core.flow_policy.start_run",
	"frappe.desk.doctype.dashboard_chart.dashboard_chart.get": "ione_core.dashboard.get_dashboard_chart",
}

scheduler_events = {
	"hourly": ["ione_core.ai.expire_pending_approvals"],
}
