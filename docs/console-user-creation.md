# Console user creation

The User ProTable opens a `DrawerForm` for creating accounts. Backend adapters are
in `ione_core.console_user_creation`; upstream Frappe code and existing role
grants remain unchanged.

`get_creation_options` returns the session user's create and role-field write
capabilities. Role choices use Frappe's native active/domain-filtered catalog and
are exposed only to callers permitted to assign User roles. Automatic or disabled
roles do not grant creation access. Configured, unmuted outgoing mail is required
to offer invitation mode.

`create_user` accepts POST only, using the existing session and CSRF validation.
It checks capabilities again, accepts a fixed field allowlist, validates duplicate
identities and password confirmation, then calls `User.insert()` without
`ignore_permissions`. Native password strength, account type derivation,
notification setup and password hashing remain active. No supplied `user_type`,
owner, flags or role profiles can bypass field permissions. Passwords are never
returned.

Basic creators can create accounts with initial passwords but cannot add roles.
An account without a desk-access role becomes a Website User and cannot log into
the console. Authorized role managers can assign active roles during creation;
the native controller derives System User status from those roles. Disabled users
cannot use invitation mode. Native invitation failures fail the request so its
transaction rolls back; success means the invitation was accepted by the native
mail flow, not a guarantee of delivery.

Field errors retain non-secret form values for correction. Closing/success clears
passwords, invitation requests omit stale password fields, and duplicate submits
are blocked while a save is pending. Permission checks are refreshed when opening
the form and repeated on POST. Successful creation refreshes the existing table.

Verification uses fictional users in the muted QA site for viewer, basic creator
and role-manager cases. Production verification opens the form and reads options
without creating users or sending email.
