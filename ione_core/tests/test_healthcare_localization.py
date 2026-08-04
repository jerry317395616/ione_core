from unittest import TestCase

from ione_core.translation_overrides import read_translation_catalog


class TestHealthcareLocalization(TestCase):
	def setUp(self):
		self.catalog = read_translation_catalog()

	def test_workspace_uses_professional_chinese_terms(self):
		expected = {
			"Healthcare": "医疗管理",
			"Healthcare Practitioner": "医务人员",
			"Practitioner Schedule": "医务人员排班",
			"Medical Department": "医疗科室",
			"Healthcare Settings": "医疗管理设置",
			"Patient History": "患者病历",
			"Laboratory": "检验科",
			"Lab Test": "检验检查",
			"Lab Test Template": "检验项目模板",
			"Inpatient Medication Order": "住院用药医嘱",
			"Rehabilitation and Physiotherapy": "康复与理疗",
			"Therapy Session": "治疗记录",
			"Therapy Plan": "治疗计划",
			"Medication Request": "用药申请",
			"Clinical Procedure": "临床诊疗",
			"Diagnostic Report": "诊断报告",
			"Observation": "观察记录",
			"Nursing Task": "护理任务",
			"Healthcare Service Unit": "医疗服务单元",
			"Terminology Mapping": "医疗术语映射",
			"Outpatient": "门诊",
			"Inpatient": "住院",
			"Total Patients": "患者总数",
			"Open Appointments": "待就诊预约",
			"Appointments to Bill": "待计费预约",
		}

		for source, translation in expected.items():
			with self.subTest(source=source):
				self.assertEqual(self.catalog[(source, "")], translation)

	def test_healthcare_terms_do_not_keep_literal_machine_phrasing(self):
		source_terms = (
			"Healthcare",
			"Practitioner",
			"Lab Test",
			"Therapy",
			"Clinical Procedure",
			"Medical Department",
			"Patient History",
			"Medication Order",
		)
		forbidden = (
			"医疗保健从业者",
			"医疗保健服务",
			"执业医师日程",
			"实验室测试",
			"疗法会话",
			"治疗会话",
			"临床操作",
			"临床程序",
			"医疗部门",
			"患者病史",
			"用药订单",
		)
		failures = []
		for (source, _context), translation in self.catalog.items():
			if any(term in source for term in source_terms) and any(
				term in translation for term in forbidden
			):
				failures.append((source, translation))

		self.assertEqual(failures, [])
