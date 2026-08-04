import json

WORKSPACE_NAME = "Healthcare"
WORKSPACE_TITLE = "医疗管理"

NUMBER_CARD_NAMES = (
	"Total Patients",
	"Total Patients Admitted",
	"Open Appointments",
	"Appointments to Bill",
)

CHART_NAMES = ("Department wise Patient Appointments",)

SIDEBAR_WORKSPACES = (
	("医疗总览", WORKSPACE_NAME, "house"),
	("门诊管理", "Outpatient", "stethoscope"),
	("住院管理", "Inpatient", "bed"),
	("检验诊断", "Diagnostics", "microscope"),
	("康复治疗", "Rehabilitation", "heart-pulse"),
	("医保结算", "Insurance", "shield-check"),
	("基础设置", "Setup", "settings"),
)

SHORTCUT_SPECS = (
	("预约管理", "DocType", "Patient Appointment", "Orange"),
	("患者档案", "DocType", "Patient", "Blue"),
	("门诊接诊", "DocType", "Patient Encounter", "Cyan"),
	("住院登记", "DocType", "Inpatient Record", "Purple"),
	("检验检查", "DocType", "Lab Test", "Blue"),
	("康复治疗", "DocType", "Therapy Session", "Green"),
	("医保理赔", "DocType", "Insurance Claim", "Yellow"),
	("患者病历", "Page", "patient_history", "Grey"),
)

CARD_GROUPS = (
	(
		"患者与预约",
		(
			("患者档案", "DocType", "Patient"),
			("预约管理", "DocType", "Patient Appointment"),
			("医务人员", "DocType", "Healthcare Practitioner"),
			("医务人员排班", "DocType", "Practitioner Schedule"),
			("医疗科室", "DocType", "Medical Department"),
			("医疗服务单元", "DocType", "Healthcare Service Unit"),
		),
	),
	(
		"门诊诊疗",
		(
			("门诊接诊", "DocType", "Patient Encounter"),
			("生命体征", "DocType", "Vital Signs"),
			("临床诊疗", "DocType", "Clinical Procedure"),
			("服务申请", "DocType", "Service Request"),
			("用药申请", "DocType", "Medication Request"),
			("收费有效期", "DocType", "Fee Validity"),
		),
	),
	(
		"住院与护理",
		(
			("住院登记", "DocType", "Inpatient Record"),
			("住院医嘱", "DocType", "Inpatient Medication Order"),
			("住院给药", "DocType", "Inpatient Medication Entry"),
			("护理任务", "DocType", "Nursing Task"),
			("医疗活动", "DocType", "Healthcare Activity"),
			("护理清单模板", "DocType", "Nursing Checklist Template"),
		),
	),
	(
		"检验与诊断",
		(
			("检验检查", "DocType", "Lab Test"),
			("样本采集", "DocType", "Sample Collection"),
			("诊断报告", "DocType", "Diagnostic Report"),
			("观察记录", "DocType", "Observation"),
			("检验报告", "Report", "Lab Test Report"),
			("诊断趋势", "Report", "Diagnosis Trends"),
		),
	),
	(
		"康复治疗",
		(
			("治疗计划", "DocType", "Therapy Plan"),
			("治疗记录", "DocType", "Therapy Session"),
			("患者评估", "DocType", "Patient Assessment"),
			("治疗类型", "DocType", "Therapy Type"),
			("运动类型", "DocType", "Exercise Type"),
			("治疗计划模板", "DocType", "Therapy Plan Template"),
		),
	),
	(
		"医保与结算",
		(
			("患者医保保单", "DocType", "Patient Insurance Policy"),
			("医保理赔", "DocType", "Insurance Claim"),
			("医保支付方", "DocType", "Insurance Payor"),
			("医保支付方合同", "DocType", "Insurance Payor Contract"),
			("患者医保保障", "DocType", "Patient Insurance Coverage"),
			("销售发票", "DocType", "Sales Invoice"),
		),
	),
	(
		"病历与报表",
		(
			("患者病历", "Page", "patient_history"),
			("患者进展", "Page", "patient-progress"),
			("患者医疗记录", "DocType", "Patient Medical Record"),
			("预约分析", "Report", "Patient Appointment Analytics"),
			("检验报告", "Report", "Lab Test Report"),
			("诊断趋势", "Report", "Diagnosis Trends"),
		),
	),
	(
		"基础资料与设置",
		(
			("医疗设置", "DocType", "Healthcare Settings"),
			("患者病历设置", "DocType", "Patient History Settings"),
			("预约类型", "DocType", "Appointment Type"),
			("医疗服务单元类型", "DocType", "Healthcare Service Unit Type"),
			("临床诊疗模板", "DocType", "Clinical Procedure Template"),
			("检验模板", "DocType", "Lab Test Template"),
		),
	),
)


def _link(label, link_type, link_to, *, icon="", child=0):
	return {
		"type": "Link",
		"label": label,
		"link_type": link_type,
		"link_to": link_to,
		"icon": icon,
		"default_workspace": 0,
		"child": child,
		"open_in_new_tab": 0,
		"collapsible": 1,
		"indent": 0,
		"keep_closed": 0,
		"show_arrow": 0,
	}


def _section(label, icon):
	return {
		"type": "Section Break",
		"label": label,
		"link_type": "DocType",
		"link_to": "",
		"icon": icon,
		"default_workspace": 0,
		"child": 0,
		"open_in_new_tab": 0,
		"collapsible": 1,
		"indent": 1,
		"keep_closed": 1,
		"show_arrow": 0,
	}


def build_sidebar_items():
	items = [_link(label, "Workspace", workspace, icon=icon) for label, workspace, icon in SIDEBAR_WORKSPACES]
	sections = (
		(
			"日常诊疗",
			"clipboard-plus",
			(
				("患者档案", "DocType", "Patient"),
				("预约管理", "DocType", "Patient Appointment"),
				("门诊接诊", "DocType", "Patient Encounter"),
				("生命体征", "DocType", "Vital Signs"),
				("临床诊疗", "DocType", "Clinical Procedure"),
			),
		),
		(
			"住院与护理",
			"bed",
			(
				("住院登记", "DocType", "Inpatient Record"),
				("住院医嘱", "DocType", "Inpatient Medication Order"),
				("住院给药", "DocType", "Inpatient Medication Entry"),
				("护理任务", "DocType", "Nursing Task"),
			),
		),
		(
			"检验与诊断",
			"microscope",
			(
				("检验检查", "DocType", "Lab Test"),
				("样本采集", "DocType", "Sample Collection"),
				("诊断报告", "DocType", "Diagnostic Report"),
				("观察记录", "DocType", "Observation"),
			),
		),
		(
			"康复管理",
			"activity",
			(
				("治疗计划", "DocType", "Therapy Plan"),
				("治疗记录", "DocType", "Therapy Session"),
				("患者评估", "DocType", "Patient Assessment"),
			),
		),
		(
			"医保与收费",
			"badge-dollar-sign",
			(
				("患者医保保单", "DocType", "Patient Insurance Policy"),
				("医保理赔", "DocType", "Insurance Claim"),
				("医保支付方", "DocType", "Insurance Payor"),
				("销售发票", "DocType", "Sales Invoice"),
			),
		),
		(
			"病历与报表",
			"file-chart-column",
			(
				("患者病历", "Page", "patient_history"),
				("患者进展", "Page", "patient-progress"),
				("预约分析", "Report", "Patient Appointment Analytics"),
				("检验报告", "Report", "Lab Test Report"),
				("诊断趋势", "Report", "Diagnosis Trends"),
			),
		),
		(
			"机构与设置",
			"building-2",
			(
				("医务人员", "DocType", "Healthcare Practitioner"),
				("医疗科室", "DocType", "Medical Department"),
				("医疗服务单元", "DocType", "Healthcare Service Unit"),
				("医疗设置", "DocType", "Healthcare Settings"),
			),
		),
	)
	for label, icon, links in sections:
		items.append(_section(label, icon))
		items.extend(
			_link(item_label, link_type, link_to, child=1) for item_label, link_type, link_to in links
		)
	return items


def build_workspace_links():
	items = []
	for label, links in CARD_GROUPS:
		items.append(
			{
				"type": "Card Break",
				"label": label,
				"hidden": 0,
				"link_type": "DocType",
				"link_count": len(links),
				"onboard": 0,
				"is_query_report": 0,
			}
		)
		for item_label, link_type, link_to in links:
			items.append(
				{
					"type": "Link",
					"label": item_label,
					"hidden": 0,
					"link_type": link_type,
					"link_to": link_to,
					"link_count": 0,
					"onboard": 0,
					"is_query_report": link_type == "Report",
				}
			)
	return items


def build_workspace_content():
	blocks = [
		{
			"id": "healthcare-overview-header",
			"type": "header",
			"data": {"text": '<span class="h4"><b>医疗运营总览</b></span>', "col": 12},
		}
	]
	for index, name in enumerate(NUMBER_CARD_NAMES, 1):
		blocks.append(
			{
				"id": f"healthcare-number-card-{index}",
				"type": "number_card",
				"data": {"number_card_name": name, "col": 3},
			}
		)
	blocks.append(
		{
			"id": "healthcare-appointment-chart",
			"type": "chart",
			"data": {"chart_name": CHART_NAMES[0], "col": 12},
		}
	)
	blocks.extend(
		[
			{"id": "healthcare-shortcut-spacer", "type": "spacer", "data": {"col": 12}},
			{
				"id": "healthcare-shortcut-header",
				"type": "header",
				"data": {"text": '<span class="h4"><b>快捷操作</b></span>', "col": 12},
			},
		]
	)
	for index, spec in enumerate(SHORTCUT_SPECS, 1):
		blocks.append(
			{
				"id": f"healthcare-shortcut-{index}",
				"type": "shortcut",
				"data": {"shortcut_name": spec[0], "col": 3},
			}
		)
	blocks.extend(
		[
			{"id": "healthcare-card-spacer", "type": "spacer", "data": {"col": 12}},
			{
				"id": "healthcare-card-header",
				"type": "header",
				"data": {"text": '<span class="h4"><b>业务中心</b></span>', "col": 12},
			},
		]
	)
	for index, group in enumerate(CARD_GROUPS, 1):
		blocks.append(
			{
				"id": f"healthcare-card-{index}",
				"type": "card",
				"data": {"card_name": group[0], "col": 4},
			}
		)
	return json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))


def ensure_healthcare_workspace():
	import frappe

	if "healthcare" not in frappe.get_installed_apps() or not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return {"status": "skipped", "reason": "Healthcare is not installed"}

	missing = []
	for _label, workspace_name, _icon in SIDEBAR_WORKSPACES:
		if not frappe.db.exists("Workspace", workspace_name):
			missing.append(f"Workspace:{workspace_name}")
	for name in NUMBER_CARD_NAMES:
		if not frappe.db.exists("Number Card", name):
			missing.append(f"Number Card:{name}")
	for name in CHART_NAMES:
		if not frappe.db.exists("Dashboard Chart", name):
			missing.append(f"Dashboard Chart:{name}")
	for _label, link_type, link_to in {entry for group in CARD_GROUPS for entry in group[1]} | {
		spec[:3] for spec in SHORTCUT_SPECS
	}:
		if link_type == "DocType" and not frappe.db.exists("DocType", link_to):
			missing.append(f"DocType:{link_to}")
		elif link_type == "Report" and not frappe.db.exists("Report", link_to):
			missing.append(f"Report:{link_to}")
		elif link_type == "Page" and not frappe.db.exists("Page", link_to):
			missing.append(f"Page:{link_to}")
	if missing:
		raise RuntimeError(f"Healthcare workspace has unavailable links: {', '.join(sorted(missing))}")

	workspace = frappe.get_doc("Workspace", WORKSPACE_NAME)
	workspace.update(
		{
			"title": WORKSPACE_TITLE,
			"label": WORKSPACE_TITLE,
			"type": "Workspace",
			"icon": "heart-pulse",
			"app": "healthcare",
			"public": 1,
			"content": build_workspace_content(),
		}
	)
	workspace.set("shortcuts", [])
	for label, link_type, link_to, color in SHORTCUT_SPECS:
		workspace.append(
			"shortcuts",
			{
				"type": link_type,
				"link_to": link_to,
				"doc_view": "List" if link_type == "DocType" else "",
				"label": label,
				"color": color,
				"stats_filter": "[]",
			},
		)
	workspace.set("links", build_workspace_links())
	workspace.set("sidebar_items", build_sidebar_items())
	workspace.set(
		"number_cards",
		[{"number_card_name": name, "label": name} for name in NUMBER_CARD_NAMES],
	)
	workspace.set(
		"charts",
		[{"chart_name": name, "label": name} for name in CHART_NAMES],
	)
	previous_in_migrate = frappe.flags.in_migrate
	frappe.flags.in_migrate = True
	try:
		workspace.save(ignore_permissions=True)
	except Exception as exc:
		raise RuntimeError(f"Unable to configure Workspace {WORKSPACE_NAME}: {exc}") from exc
	finally:
		frappe.flags.in_migrate = previous_in_migrate
	frappe.db.set_value(
		"Workspace",
		WORKSPACE_NAME,
		{
			"label": WORKSPACE_TITLE,
			"title": WORKSPACE_TITLE,
			"type": "Workspace",
			"app": "healthcare",
		},
		update_modified=False,
	)
	return {"status": "updated", "workspace": WORKSPACE_NAME}
