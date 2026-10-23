# Deployment components and configuration archives

These directories have different scopes; none is invoked automatically by the
application's install or migration hooks.

- [DingTalk Stream](dingtalk_stream/README.md): a separately configured Linux
  receiver, durable inbox and import gate. Site scheduling is explicitly opt-in;
  see its configuration instructions before upgrading an existing integration.
- [Native meal pilot](erp_meal_week_sample_20261022/README.md): the final report,
  calendar, field and client-script definitions for a fixed demonstration week.
  This archive does not create recipes, business documents or user grants, and
  does not implement procurement or nutrition analysis.
- [Official UI restoration](official_ui_restore_20261022/README.md): a historical
  patch to site-specific I-ONE customizations. It is not a patch to the official
  Frappe applications or an installer for the current repository revision.

The HRMS recurring shift compatibility extension is documented separately in
[HRMS shift-cycle compatibility](../docs/hrms-shift-cycle-compat.md).

Production credentials, users, employee mappings, check-in records, source
spreadsheets, screenshots, database backups and private deployment receipts are
deliberately excluded. Publishing these files to GitHub does not redeploy the
running site.
