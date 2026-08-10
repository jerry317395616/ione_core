# I-ONE Core

I-ONE Core is the Frappe service layer for the I-ONE AI workbench. It keeps
identity, permissions, business links, AI jobs, approvals, audit logs, and
cross-application dashboard data in Frappe while reusing ERPNext and the
installed Frappe products as the system of record.

## Flow department execution policies

`I-ONE Flow Execution Policy` controls Flow approvals by ERPNext Department
without changing Flow itself. A policy can keep all confirmations, auto-run
selected tools, or auto-run every tool. Policies can apply independently to
Desk Flow and I-ONE AI employees. Child departments inherit the nearest
enabled parent policy, while an exact department policy takes precedence.

Users are matched through their active Employee record. When no Employee is
linked, I-ONE checks the user's default Department or default Department user
permission, then falls back to a root Department policy.

## Chinese localization bundle

`ione_core/translations/zh.csv` is the version-controlled source of truth for
Chinese interface translations. Installing or migrating I-ONE Core synchronizes
the complete catalog into Frappe's `Translation` records, preserves literal
technical markup, and removes equivalent duplicate keys. A first-time install
also selects Chinese for System Settings and the Administrator user; later
migrations do not overwrite users' language choices. To append translations
created on a maintained source site without replacing curated application values:

```bash
bench --site manager.myyr.top execute ione_core.translation_overrides.export_site_translation_catalog
```

Translated Wiki spaces can be exported into the checksummed
`ione_core/translation_data` bundle. I-ONE Core imports new bundle versions
during installation or migration, also imports them when Wiki is installed
later, and skips bundles already present on the site:

```bash
bench --site manager.myyr.top execute ione_core.translation_bundle.export_translation_bundle
```
