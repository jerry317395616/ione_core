from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
import zipfile
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.identity import verify_actor_token
from ione_core.mcp.lead_analysis import create_lead_analysis_docx, validate_analysis
from ione_core.mcp.security import extract_docx_text


SECRET = "test-identity-secret-that-is-longer-than-thirty-two-characters"


def sample_analysis() -> dict:
	sections = []
	for index, title in enumerate(
		(
			"客户与线索概况",
			"业务背景与触发事件",
			"显性需求",
			"隐性需求与根因",
			"现状流程与核心痛点",
			"目标与成功指标",
			"利益相关者与决策链",
			"需求优先级",
			"建议解决思路",
			"数据、集成与合规要求",
			"风险、假设与待确认事项",
			"推荐跟进计划",
		),
		start=1,
	):
		sections.append(
			{
				"title": title,
				"paragraphs": [
					f"第{index}部分基于现有线索事实进行分析，明确已知信息、合理推断和待客户确认事项。"
					"分析覆盖业务流程、组织协作、数据质量、系统集成、合规约束和实施节奏，"
					"并给出可验证的下一步动作，避免把未经证实的假设表述为客户事实。"
				],
				"bullets": [
					"已知事实：来源清晰、可回溯，并保留原始资料依据。",
					"分析判断：说明判断逻辑、业务影响和验证方法。",
					"待确认：在首次沟通中核实负责人、预算、时间和验收口径。",
				],
			}
		)
	return {
		"report_title": "医疗客户需求分析报告",
		"executive_summary": [
			"客户正在评估以数据驱动方式改进业务协同，当前线索显示其重点关注效率、质量和合规。",
			"建议先完成需求澄清和决策链确认，再以可量化的小范围场景验证价值并形成实施路线图。",
		],
		"sections": sections,
		"sources": ["客户公开招标信息，访问日期：2026-08-08", "CRM 线索原始资料"],
	}


def issue_token(*, email: str, site: str, now: int) -> str:
	payload = {
		"v": 1,
		"iss": "ione-agent",
		"aud": site,
		"email": email,
		"iat": now,
		"exp": now + 600,
	}
	raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
	segment = base64.urlsafe_b64encode(raw).decode().rstrip("=")
	signed = f"ione1.{segment}"
	signature = hmac.new(SECRET.encode(), signed.encode(), hashlib.sha256).digest()
	return f"{signed}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


class TestLeadAnalysisWord(TestCase):
	def test_renders_detailed_analysis_as_readable_docx(self):
		payload = create_lead_analysis_docx(
			sample_analysis(),
			lead_name="CRM-LEAD-2026-00042",
			customer_name="示例医疗集团",
			prepared_for="owner@example.com",
		)
		self.assertTrue(payload.startswith(b"PK\x03\x04"))
		with zipfile.ZipFile(BytesIO(payload)) as archive:
			self.assertIsNone(archive.testzip())
			self.assertIn("word/document.xml", archive.namelist())
		text = extract_docx_text(payload)
		self.assertIn("医疗客户需求分析报告", text)
		self.assertIn("CRM-LEAD-2026-00042", text)
		self.assertIn("风险、假设与待确认事项", text)

	def test_rejects_shallow_analysis(self):
		analysis = sample_analysis()
		analysis["sections"] = analysis["sections"][:2]
		with self.assertRaisesRegex(ValueError, "at least 10 sections"):
			validate_analysis(analysis)


class TestActorIdentity(TestCase):
	def fake_frappe(self):
		frappe = ModuleType("frappe")
		frappe.conf = {"ione_agent_identity_shared_secret": SECRET}
		frappe.local = SimpleNamespace(site="manager.myyr.top")
		frappe.AuthenticationError = type("AuthenticationError", (Exception,), {})
		frappe.PermissionError = type("PermissionError", (Exception,), {})

		def throw(message, exc=None):
			raise (exc or ValueError)(message)

		frappe.throw = throw
		return frappe

	def test_accepts_current_manager_identity(self):
		now = int(time.time())
		token = issue_token(email="owner@example.com", site="manager.myyr.top", now=now)
		with patch.dict(sys.modules, {"frappe": self.fake_frappe()}):
			payload = verify_actor_token(token, now=now)
		self.assertEqual(payload["email"], "owner@example.com")

	def test_rejects_identity_for_another_site(self):
		now = int(time.time())
		token = issue_token(email="owner@example.com", site="other.example", now=now)
		with patch.dict(sys.modules, {"frappe": self.fake_frappe()}):
			with self.assertRaisesRegex(Exception, "different site"):
				verify_actor_token(token, now=now)

	def test_rejects_tampered_identity(self):
		now = int(time.time())
		token = issue_token(email="owner@example.com", site="manager.myyr.top", now=now)
		tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
		with patch.dict(sys.modules, {"frappe": self.fake_frappe()}):
			with self.assertRaisesRegex(Exception, "invalid"):
				verify_actor_token(tampered, now=now)
