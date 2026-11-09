# Console user role assignment

The User ProTable opens a separate `DrawerForm` for existing accounts. All server
adapters are in `ione_core.console_user_roles`; upstream Frappe is unchanged.

`get_role_access` uses the logged-in user's enabled roles and effective User
metadata. Viewing requires User read and read access to the `roles` field
(currently permission level 1). Editing also requires field write and document
write. Each target is checked with native document permissions, including owner
and User Permission restrictions. The list action is only a capability hint;
opening and saving both recheck the actual target. No existing grants are added.

`get_user_roles` returns minimal account information and assigned roles. Read-only
callers receive no role or profile catalogs. Administrator and Guest are always
read-only here; native User permissions also restrict viewing those records.
Nonstandard user types are read-only. Automatic roles (All, Guest and Desk User)
are displayed separately and cannot be manually assigned.

Editors may use direct roles or multiple Role Profiles. Profile choices require
access to Role Profile and write access to User's `role_profiles` field. Role
choices use the native active/domain-filtered catalog. Profiles containing
unassignable roles are disabled and rejected on save. Profile roles are combined
by the native User controller. Switching to direct assignment prepopulates the
combined roles and clears both modern and deprecated profile associations.
Existing profile assignments cannot be changed without profile-field write.

`save_user_roles` accepts POST with the existing session and native CSRF
validation. It accepts only the target, modification stamp, role source, role
names/profile names and the desk-access confirmation. The server compares the
stamp and calls `User.save()` without permission bypasses; the native save also
checks concurrent updates. It then clears the target user's permission cache.
The response contains no passwords or unrelated User fields.

Removing all desk-access roles from a System User requires an explicit modal
confirmation and a strict boolean confirmation on the server. Frappe derives
Website User status from the resulting roles. The drawer warns before saving;
stale records retain the current form and offer reload. Successful saves refresh
the table and the actor's capabilities. Permission changes affect refreshed
navigation and subsequent permission-checked requests.

Verification covers basic, read-only, editing and owner-restricted actors in a
muted QA site. Browser checks cover profile union, direct assignment, detaching
profiles, concurrent saves, confirmation cancellation/acceptance and mobile
layout. Production checks read capabilities and the list without changing any
real user's roles or permission grants.
