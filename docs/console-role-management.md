# Console role management

The Role list adds create/edit drawers, a rename dialog and a typed-confirmation
delete dialog. `ione_core.console_role_management` keeps all adaptations outside
upstream Frappe. The existing read-only endpoints remain available.

Session capabilities come from enabled business roles and effective Role metadata.
Role create/write/delete grants are checked independently; each record also needs
native document permissions. Both list and detail use the same strict read query,
including owner, User Permission and sharing conditions, so link selection cannot
broaden detail access. Field mutations use a fixed allowlist and native field
permission levels. Create allows level-0 fields under create permission; editing
requires their write levels. `is_custom`, grants, members, owner and bypass flags
cannot be submitted. Domain choices require native Domain read/select access and
default home pages must be safe site-local paths.

Reserved roles (native STANDARD_ROLES plus AUTOMATIC_ROLES) are read-only here.
Roles assigned to the current actor cannot be deleted or renamed. Their disabled,
desk-access removal and domain changes are also blocked, while ordinary settings
remain editable when authorized. The policy does not hardcode a hospital role name.

All writes lock the Role row and compare the client's modification stamp. Create
uses native insert, update uses native save, rename uses native rename without
merging/force, and delete uses native delete without ignoring permissions or links.
Rename updates stored identifiers and references and advances the edit stamp
without rerunning disabled-role validation. Native change history, rename comments
and recoverable deletion records remain in effect.

Disabled state, desk access, domain and two-factor requirements have a separate
impact preview. Its opaque, five-minute token is bound to the actor, session,
version, submitted values, association rows, parent versions and role permission
rule versions. Save recomputes the intent and rejects stale or replayed previews.
Only counts of readable users/profiles with readable role fields are returned;
hidden associations and other record types receive generic indicators. Disabling
uses Frappe's native removal of all Has Role links. Changing desk access keeps the
native account-type recalculation and nested User permission checks; a failed
request rolls back the transaction instead of elevating the actor.

Deletion requires an exact identifier confirmation. Has Role, DocPerm and Custom
DocPerm references always block it, followed by native static/dynamic link checks.
Preflight and execution both check references; no member or grant is removed on
the caller's behalf. Cache invalidation runs immediately and after commit.

QA verification uses fictional actors and records in the muted, paused test site.
Production verification reads capabilities and opens/cancels forms without
creating, changing, renaming or deleting real roles or changing any grants.
