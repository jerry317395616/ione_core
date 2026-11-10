# Console role business permissions

The Role list opens a full-page permission matrix through `permission_role` in
the current console URL. ProTable shows level-0 rules without an owner constraint;
an advanced drawer edits native field levels, owner rules and applicable rights.
Drafts stay local until a server-generated preview is confirmed. Leaving with
drafts prompts for confirmation. Read-only delegates and protected roles keep
the same view with editing disabled.

All Frappe adaptation belongs to `ione_core`; see the repository `AGENTS.md`.
The React source remains in the user's Ant Design Pro project. No upstream
Frappe/ERPNext/Healthcare source or native permission-manager endpoint is patched.

## Administration authority

Role create/write/delete does **not** authorize permission configuration.
`I-ONE Permission Administration` explicitly delegates view or edit access to
business modules through an active manager role. Only Administrator and active
System Managers may maintain these grants, including through native resource
APIs. Grant records themselves cannot be business targets. The backend derives
authority from current enabled roles and current grants on every request, never
from a hospital role's name or client capability flags.

Ordinary delegates are limited to explicitly listed modules in installed apps
other than Frappe. Core system objects (User, Role, DocType, permission rules,
scripts and framework settings) are outside that delegation. Native System
Managers/Administrator retain their broader system authority, with the console's
reserved-role and native custom-user-type role protections. Disabled roles are
read-only. Role list/detail read scope must also permit the selected role.

Provision explicitly as an authorized operator after syncing the new DocTypes:

```python
from ione_core.console_permission_policy import provision_business_manager
provision_business_manager("Your existing management role", modules=["Rehab"])
```

Omitting `modules` selects the currently installed business modules. Future
modules are not silently added. Install/migrate does not assign management
authority to any role. This delegation grants configuration ability, not access
to the underlying clinical or business records; it does not add System Manager.

## Native rule persistence

Rules are stored in native Custom DocPerm and evaluated by Frappe. Once custom
rules exist for a DocType they replace the whole default matrix. The first edit
therefore uses `setup_custom_perms` to copy **all** defaults, and subsequently
changes only the selected role's rows. Removing a role's final row leaves other
roles intact and does not reactivate standard defaults. Removing the DocType's
last permission rule is rejected. This UI has no whole-DocType reset action.

Native unsaved DocType validation checks the selected role's rules before any
write. It enforces dependencies, field levels and supported operations without
rewriting other roles' rows. Owner-only rules are level 0 and cannot grant report
access. Higher levels edit read/write/mask; unchanged legacy extra flags are
preserved and can be revoked. Mask access permits reading the unmasked value.
An owner condition refers to the record creator, not its assigned clinician.

Saving requires a five-minute, random confirmation token bound to the actor,
session, selected role/version and exact before/after changes. Every submitted
DocType has a fingerprint covering all its standard/custom rules and relevant
field metadata. Rows are sorted before hashing because native child-table reads
and locking queries have different default order. Save locks the Role, DocTypes
and permission rows in deterministic parent order, rechecks scope and versions,
and applies the entire batch in a single native POST transaction. Invalid or
concurrent edits roll back. Batches are limited to 100 objects.

The adapter's internal native Custom DocPerm lifecycle writes use an explicit
permission bypass only **after** this separate administration authorization and
scope validation; it never changes the session identity or accepts bypass flags.
Native Permission Log entries retain the real actor. Preview association counts
only include readable users/profiles with readable role fields; other references
are indicated without leaking identities. Cache invalidation runs immediately
and after commit. The console refreshes its current application menus after save.

The editor shows this role's explicit rules. A user's effective access still
combines all roles, field levels, user permissions, domain and application state,
and native business controller/query conditions. Data-range administration is
not replaced by this matrix.
