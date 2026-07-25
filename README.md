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
