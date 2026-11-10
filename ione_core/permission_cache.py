"""Invalidate worker-local authorization caches after committed permission changes.

Redis client-cache invalidation is asynchronous and its listener may be absent in
preloaded/forked workers. A site revision is checked at every request so a worker
cannot keep its ten-minute local metadata cache after an authorization change.
"""

import os
import secrets
from threading import RLock

import frappe

REVISION_KEY = "ione_permission_revision"
_seen = {}
_lock = RLock()


def ensure_current():
	revision = frappe.cache.get_value(REVISION_KEY, use_local_cache=False)
	if not revision:
		return
	key = (os.getpid(), frappe.local.site)
	with _lock:
		if _seen.get(key) == revision:
			return
		frappe.client_cache.clear_cache()
		frappe.local.cache = {}
		frappe.local.role_permissions = {}
		if hasattr(frappe.local, "request_cache"):
			frappe.local.request_cache.clear()
		_seen[key] = revision


def publish_revision():
	# A Custom DocPerm deletion does not run its on_update parent invalidation.
	# Invalidate the parent metadata in Redis before announcing the new revision,
	# otherwise another worker would simply reload the stale granted rule.
	for doctype in frappe.flags.pop("ione_permission_doctypes", set()):
		from frappe.core.doctype.doctype.doctype import clear_permissions_cache

		clear_permissions_cache(doctype)
	frappe.cache.set_value(REVISION_KEY, secrets.token_hex(16))
	frappe.flags.ione_permission_revision_pending = False
	ensure_current()


def schedule_refresh(doc=None, method=None):
	if doc and getattr(doc, "doctype", None) == "Custom DocPerm" and doc.parent:
		frappe.flags.setdefault("ione_permission_doctypes", set()).add(doc.parent)
	if frappe.flags.get("ione_permission_revision_pending"):
		return
	frappe.flags.ione_permission_revision_pending = True
	frappe.db.after_commit.add(publish_revision)
	frappe.db.after_rollback.add(cancel_refresh)


def cancel_refresh():
	frappe.flags.pop("ione_permission_revision_pending", None)
	frappe.flags.pop("ione_permission_doctypes", None)
