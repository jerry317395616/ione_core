"""Opt-in scheduled entry points for sites using the DingTalk integration.

Installing I-ONE Core must not activate attendance imports on other sites.
Manual methods and the durable Stream worker retain their existing behavior.
"""

import frappe


def _enabled():
    value = frappe.conf.get("dingtalk_attendance_scheduler_enabled", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True or (type(value) is int and value == 1)


def run_daily():
    if not _enabled():
        return {"ok": True, "skipped": "scheduler_disabled"}

    from ione_core.dingtalk_attendance import sync_dingtalk_attendance_job

    return sync_dingtalk_attendance_job()


def run_catchup():
    if not _enabled():
        return {"ok": True, "skipped": "scheduler_disabled"}

    from ione_core.dingtalk_attendance import sync_dingtalk_attendance_catchup_job

    return sync_dingtalk_attendance_catchup_job()
