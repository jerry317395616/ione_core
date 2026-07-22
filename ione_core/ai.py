import json
from urllib.request import Request, urlopen

import frappe
from frappe.utils import add_to_date, now_datetime


def _log(task, event_type, message, level="信息", payload=None, duration_ms=None):
	frappe.get_doc(
		{
			"doctype": "I-ONE AI Run Log",
			"owner": task.owner,
			"task": task.name,
			"agent": task.assigned_agent,
			"event_type": event_type,
			"level": level,
			"message": message,
			"payload_json": json.dumps(payload, ensure_ascii=False) if payload is not None else None,
			"duration_ms": duration_ms,
		}
	).insert(ignore_permissions=True)


def _settings():
	return frappe.get_single("I-ONE Settings")


def call_openai_compatible(prompt, system_prompt=None, temperature=0.2):
	settings = _settings()
	base_url = (settings.llm_base_url or "").rstrip("/")
	if not base_url:
		frappe.throw("请先在 I-ONE 设置中配置模型服务地址")

	payload = {
		"model": settings.model_name or "qwen",
		"messages": [
			{
				"role": "system",
				"content": system_prompt or "你是 I-ONE 企业智能助理。输出准确、可执行，并使用中文回答。",
			},
			{"role": "user", "content": prompt},
		],
		"temperature": temperature,
	}
	headers = {"Content-Type": "application/json", "Accept": "application/json"}
	api_key = settings.get_password("api_key", raise_exception=False)
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"

	request = Request(
		f"{base_url}/chat/completions",
		data=json.dumps(payload).encode("utf-8"),
		headers=headers,
		method="POST",
	)
	with urlopen(request, timeout=300) as response:
		data = json.loads(response.read().decode("utf-8"))
	return data["choices"][0]["message"]["content"], data


def _call_openai_compatible(task, settings=None):
	return call_openai_compatible(task.prompt)


def execute_ai_task(task_name):
	task = frappe.get_doc("I-ONE AI Task", task_name)
	if task.status in {"已完成", "已取消"}:
		return

	task.db_set({"status": "执行中", "progress": 10, "started_at": now_datetime()}, update_modified=True)
	_log(task, "任务开始", "后台工作器开始执行任务")
	frappe.db.commit()

	try:
		settings = _settings()
		content, raw = _call_openai_compatible(task, settings)
		task.db_set(
			{
				"status": "已完成",
				"progress": 100,
				"result_summary": content,
				"result_json": json.dumps(raw, ensure_ascii=False),
				"completed_at": now_datetime(),
				"error_message": None,
			},
			update_modified=True,
		)
		_log(task, "任务完成", "模型返回结果并已保存")
	except Exception as exc:
		message = str(exc)[:2000]
		task.db_set(
			{
				"status": "执行失败",
				"error_message": message,
				"completed_at": now_datetime(),
			},
			update_modified=True,
		)
		_log(task, "执行失败", message, level="错误")
		frappe.log_error(title=f"I-ONE AI Task {task.name}", message=frappe.get_traceback())
	finally:
		frappe.db.commit()


@frappe.whitelist()
def queue_ai_task(title, prompt, assigned_agent=None, priority="普通", approval_required=0):
	if frappe.session.user == "Guest":
		frappe.throw("请先登录", frappe.AuthenticationError)

	requires_approval = bool(int(approval_required or 0))
	task = frappe.get_doc(
		{
			"doctype": "I-ONE AI Task",
			"title": title,
			"prompt": prompt,
			"assigned_agent": assigned_agent,
			"priority": priority,
			"requested_by": frappe.session.user,
			"approval_required": requires_approval,
			"status": "待审批" if requires_approval else "已排队",
		}
	).insert()

	if not requires_approval:
		job = frappe.enqueue(
			"ione_core.ai.execute_ai_task",
			queue="long",
			enqueue_after_commit=True,
			job_name=f"ione-ai-{task.name}",
			task_name=task.name,
		)
		task.db_set("queue_job_id", getattr(job, "id", None), update_modified=False)

	return {"name": task.name, "status": task.status}


@frappe.whitelist()
def decide_approval(approval_name, decision, note=None):
	approval = frappe.get_doc("I-ONE Approval Request", approval_name)
	if approval.status != "待审批":
		frappe.throw("该审批已经处理")
	if frappe.session.user not in {approval.approver, "Administrator"} and "I-ONE Manager" not in frappe.get_roles():
		frappe.throw("您没有权限处理该审批", frappe.PermissionError)

	if decision not in {"批准", "拒绝"}:
		frappe.throw("无效的审批决定")
	approval.db_set(
		{
			"status": decision,
			"decision_note": note,
			"decided_at": now_datetime(),
		},
		update_modified=True,
	)

	if decision == "批准" and approval.task:
		task = frappe.get_doc("I-ONE AI Task", approval.task)
		task.db_set("status", "已排队")
		if task.source_doctype == "I-ONE Smart Record" and task.source_name:
			frappe.db.set_value("I-ONE Smart Record", task.source_name, "status", "执行中")
			frappe.enqueue(
				"ione_core.smart_record.execute_smart_record_job",
				queue="long",
				enqueue_after_commit=True,
				job_name=f"ione-smart-execution-{task.source_name}",
				record_name=task.source_name,
				task_name=task.name,
			)
		else:
			frappe.enqueue(
				"ione_core.ai.execute_ai_task",
				queue="long",
				enqueue_after_commit=True,
				job_name=f"ione-ai-{task.name}",
				task_name=task.name,
			)
	elif approval.task:
		task = frappe.get_doc("I-ONE AI Task", approval.task)
		frappe.db.set_value("I-ONE AI Task", task.name, "status", "已取消")
		if task.source_doctype == "I-ONE Smart Record" and task.source_name:
			frappe.db.set_value("I-ONE Smart Record", task.source_name, "status", "已取消")

	return {"name": approval.name, "status": decision}


def expire_pending_approvals():
	if not frappe.db.exists("DocType", "I-ONE Approval Request"):
		return
	cutoff = now_datetime()
	for name in frappe.get_all(
		"I-ONE Approval Request",
		filters={"status": "待审批", "expires_at": ["<", cutoff]},
		pluck="name",
	):
		frappe.db.set_value(
			"I-ONE Approval Request",
			name,
			{"status": "已过期", "decided_at": cutoff},
			update_modified=False,
		)


def default_approval_expiry():
	return add_to_date(now_datetime(), hours=24)
