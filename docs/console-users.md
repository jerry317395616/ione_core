# Console user list

`ione_core.console_users.get_users` is a read-only GET endpoint for ProTable.
It requires an enabled System User and effective User read access. It returns
`{data, total, success}`, with at most 100 records per page, fixed fields and
allowlisted sort/filter parameters. Passwords, API credentials and reset tokens
are never selected. Native field permissions can omit a column such as
`user_type`; the frontend displays an empty value rather than fetching it through
an elevated query.

Rows and totals both use the native Frappe query engine, including field masks,
User Permissions, permission hooks and document sharing. A scoped Engine subclass
keeps owner-only **read** constraints even when the user's automatic Desk User
role permits unrestricted **select** for Link fields. No role grant or upstream
query engine change is required.

The console application context includes an optional semantic `target` on each
permitted menu item. The frontend mounts User ProTable for `DocType / User`,
independently of translated labels or sidebar occurrence. Existing menu IDs and
hierarchy remain unchanged.

Checks:

```sh
python -m unittest ione_core.tests.test_console_users ione_core.tests.test_navigation -v
```

Integration verification uses fictional identities in the muted QA site: a User
reader, an owner-only reader, and a user with no User read permission. It checks
pagination and totals, wildcard escaping, filters, native field omissions, and
that owner-only reading returns one record despite unrestricted Link selection.
Browser checks cover search, pagination, sorting, empty/error states, retry,
session expiry and the mobile table.
