import frappe
from frappe.model.document import Document


class IONEEmployeeDirectory(Document):
	def validate(self):
		frappe.throw("请通过新前端维护原生员工档案。")
