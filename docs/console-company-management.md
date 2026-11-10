# Console company management and application navigation

Authorized business applications now reuse native sidebar projection instead of
being rejected by the former Frappe-only check. Native permission/domain/module
filters still run first. Companion sidebars use the native app-rail host mapping.
Application membership still requires an explicit business-role grant to an item
owned by that app; an incidental framework link never opens another application.

The console renders Company targets as a ProTable and a create/view/edit drawer.
Basic fields include country, currency, company type/parent, valuation method,
tax identifier and contact details. Existing company identity, abbreviation and
group status are not changed here. Rename, deletion and advanced financial setup
are outside this first company form. Other authorized menus retain their existing
placeholder until their specific page is implemented. No action jumps to Desk.

`ione_core.console_companies` independently derives read/create/write capabilities
from active business roles and effective native permissions. Owner-only write is
checked per record. The same strict native query controls list rows, totals and
detail availability, preserving owner restrictions even when link selection is
unrestricted, as well as User Permission and native query/controller conditions.
Field levels and masking control returned fields and write allowlists.

Creation uses normal native insert; editing locks the row, compares the original
modification stamp and uses normal native save. There is no permission/lifecycle
bypass, financial initialization flag or caller-supplied owner. ERPNext owns its
account/warehouse/cost-center initialization and validations. Submitted fields
have a fixed allowlist. Changed links use native scoped link search; parent
companies additionally use the strict readable group-company query. Translated
masters support both labels and raw IDs; exact validation filters by the stored
name without applying a translated-label text filter. Unchanged links are not
cleared merely because their lookup options are no longer available.

## Permission cache consistency

Native Redis client caches have worker-local copies, and asynchronous invalidation
may be unavailable in preloaded/forked workers. `ione_core.permission_cache` adds
a site revision checked by a before-request hook using a non-local Redis read.
A new revision clears that worker's client cache and request permission caches.
The process ID and site identify the worker revision state. Unchanged revisions
do not repeatedly flush worker caches.

Native Custom DocPerm saves/deletions, Role updates, User updates and User
Permission changes schedule one revision after transaction commit. Rollback
cancels the revision. Affected permission-parent metadata is invalidated before
publishing the revision: Custom DocPerm deletion does not call its on_update
parent invalidation, so clearing only the child metadata would reload stale
grants from Redis. The revision key survives ordinary full-site cache clearing.
The console permission editor explicitly schedules the same commit notification.

QA uses muted, paused test-site actors and synthetic companies. API checks cover
native initialization, read-only/owner/user/field scope, stale edits and link
selection. A separate persistent process deliberately disables its invalidation
listener and proves both grant and revocation. Browser checks cover navigation,
create/edit, duplicate-abbreviation retry with retained values, read-only fields
and mobile layout. Production verification only reads and opens/cancels forms;
real companies and role grants are preserved.
