# Effective permission navigation

`ione_core.navigation` supplies one visibility policy for native Desk and the custom
console. It does not grant roles or replace document/API authorization.

* Disabled roles and Frappe's automatic roles (`All`, `Guest`, `Desk User`) do not
  establish business application membership. Effective level-zero read permissions
  come from Frappe's `get_valid_perms`, including Custom DocPerm replacement rules.
* Native sidebar resolution runs first. Domain restrictions, blocked modules,
  user permissions, disabled apps and sidebar arrangements still apply. Each
  remaining DocType entry also passes the native read check.
* Reports need a permitted reference DocType; Pages need an explicit effective
  Page/Custom Role grant. Workspaces and dashboards qualify through permitted
  contents. Workspace cycles and URL/help-only shells cannot establish access.
* At least one qualified target owned by an application must exist to show that
  application. A User shortcut curated into ERPNext Setup therefore does not make
  ERPNext visible to someone with only User permission. Native permitted shared
  entries remain in applications that have qualified business access.
* Installed/active, setup, companion/docked and site-hidden app rules remain in
  effect. For Desk applications, actual business entries replace coarse app-hook
  role-name checks. Non-Desk applications retain their app-specific hook as an
  additional gate. The built-in `Administrator` retains native recovery access;
  an ordinary account named `admin` does not acquire that exception.
* Native section/child relationships, ordering and console menu identities remain
  stable. Empty sections, modules and applications disappear. Restricted users
  land in a permitted shell rather than the app's potentially inaccessible setup
  page. Account/profile conveniences remain part of the existing account UI.

The hooks adapt native boot/dock/route maps and JSON navigation refreshes after
workspace/sidebar writes. Whitelisted overrides cover `frappe.apps.get_apps`
(GET and POST) and the existing `rehab.frontend_auth.get_apps` / `get_application`
console URLs. Console application contents retain their existing implementation
scope: Framework modules are implemented; other applications keep their current
placeholder. No upstream Frappe, ERPNext, Healthcare, HRMS or Rehab source edit is
needed. No frontend bundle replacement is needed.

For the current role with one User read grant, the expected navigation is
Framework → Users → User. Adding an Account read grant adds ERPNext navigation;
removing/disabling the grant removes it again. User record/data restrictions and
write/create/delete permissions continue to be enforced by native APIs.

Run the isolated unit checks from this repository:

```sh
python -m unittest ione_core.tests.test_navigation ione_core.tests.test_install_hooks -v
ruff check ione_core/navigation.py ione_core/hooks.py ione_core/tests/test_navigation.py
```

On deployment, clear the site's Frappe cache and restart its web processes to
refresh whitelisted overrides and existing boot caches. Rollback consists of
reverting the navigation module/hook change, clearing the cache and restarting
the same web service; there are no schema changes or role migrations.
