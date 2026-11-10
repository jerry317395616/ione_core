import frappe
from frappe.model.document import Document


class IONEPermissionAdministration(Document):
	def validate(self):
		from ione_core.console_permission_policy import business_modules, require_supervisor

		require_supervisor()
		if not self.modules or any(row.module not in business_modules() for row in self.modules):
			frappe.throw("请选择已安装业务应用中的有效模块。")
		if len({row.module for row in self.modules}) != len(self.modules):
			frappe.throw("业务模块不能重复。")

	def on_trash(self):
		from ione_core.console_permission_policy import require_supervisor

		require_supervisor()
