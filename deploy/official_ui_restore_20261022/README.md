# Official UI restoration patch — 2026-10-22

This directory records the source patch applied to the site's existing I-ONE
customizations during the official Frappe upgrade. The patch changes only
`ione_core`; it does not patch Frappe, ERPNext, HRMS or Education source files.

It removes the site's custom global navigation assets and boot/landing hooks,
stops reapplying custom desktop/navigation changes during install or migration,
and preserves the selected official workspace title and translation values.

This is a historical, manually applied patch against that site's pre-upgrade
customized source, not a migration or an installer for the current GitHub branch.
The GitHub branch has subsequently received independent changes. Do not apply
this patch blindly, replace current files with old copies, or run it from an
installation hook. Review the exact target revision and merge only the desired
site-specific behavior.

The accompanying database changes (desktop/workspace settings, translations,
user preferences and permissions) are not included. This patch alone does not
recreate or roll back that deployment. Backups and deployment receipts remain
outside the repository.

The application's current shared navigation behavior remains unchanged by
merely checking out this archive. The attendance hooks added in the surrounding
change are maintained separately in `ione_core/hooks.py`.
