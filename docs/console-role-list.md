# Console role browsing

The existing Role menu opens the custom console's ProTable. It provides translated
labels alongside stored identifiers, keyword/status/desk-access filters, native
permission-checked pagination and sorting, and a read-only details drawer. Other
menus and the native site's entry point retain their existing behavior.

Both GET adapters in `ione_core.console_roles` require an enabled System User and
an explicit enabled business role with Role read access (or Administrator).
Neither Role write permission nor User role-field write is required for browsing.
Native row permissions, User Permissions, sharing and field masking remain in
effect. Link select cannot relax owner-only read constraints. Rows and totals use
identical native query conditions. Translated keyword matching examines only
names the caller is permitted to read; it treats wildcard characters literally.

The list returns a fixed field allowlist. Details additionally check the actual
Role document and apply native field-level read permissions before projection.
No permission matrix, linked users or unrelated document fields are returned.
Responses use `private, no-store`. There are no mutation endpoints in this feature.

Reserved markers come from the union of native `STANDARD_ROLES` and
`AUTOMATIC_ROLES`. They do not use the `is_custom` flag to infer origin or grant
extra access. Disabled roles remain browsable when native read permissions allow
them. Desk access is displayed separately from business application permissions.

Permission failures, missing/deleted details and network errors have dedicated
messages and retry actions. The drawer is separate from table rendering, supports
desktop and full-width mobile sizes, and discards late responses after closing
or selecting another record. Home-page paths are rendered as plain text.

Creating/editing roles, disabling them, copying permissions and permission-matrix
editing are outside this release. In particular, native Role disabling removes
Has Role links and must be designed as a separate confirmed operation.
