"""Preserve Frappe's direct private-attachment authorization with Suite installed."""

import frappe
from frappe import share


class PrivateFileDownload:
	def is_downloadable(self):
		if not self.is_private or "suite" not in frappe.get_installed_apps():
			return super().is_downloadable()

		# Suite replaces the native File permission helper, but Frappe's
		# /private/files handler continues to call this controller method.
		user = frappe.session.user
		if user == "Administrator" or (user != "Guest" and self.owner == user):
			return True
		if user != "Guest" and share.get_shared(
			"File", filters=[["share_name", "=", self.name]], rights=["read"], user=user
		):
			return True
		if not self.attached_to_doctype or not self.attached_to_name:
			return False
		try:
			source = frappe.get_lazy_doc(self.attached_to_doctype, self.attached_to_name)
		except (ImportError, frappe.DoesNotExistError):
			return False
		return source.has_permission("read", user=user)
