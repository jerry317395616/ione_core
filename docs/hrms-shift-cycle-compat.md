# HRMS shift recurrence compatibility

`ione_core.hrms_compat.shift_schedule_assignment.PreserveShiftCycleBoundaryMixin`
preserves the processed recurrence boundary when HRMS automatically extends a
Shift Schedule Assignment. It calls the official generator through `super()`;
only after successful generation does it persist `create_shifts_after`, including
off weeks already skipped by the native loop. Assignment creation, validation,
employee, company, status, location and date ranges remain HRMS responsibilities.
The extension does not commit, delete assignments, or change existing schedules.

Register it through the standard cooperative hook in `ione_core/hooks.py`:

```python
extend_doctype_class = {
    "Shift Schedule Assignment": [
        "ione_core.hrms_compat.shift_schedule_assignment.PreserveShiftCycleBoundaryMixin"
    ]
}
```

Merge this entry with existing registrations, preserving other extensions. Do not
replace official Frappe/HRMS files or register an overriding controller. Other
cooperative mixins remain in the method resolution order.

## Compatibility and dependencies

- The hook requires Frappe v16 or newer. This is not a claim of compatibility with
  every later release: the verified source revisions are pinned below.
- HRMS must be installed on sites using Shift Schedule Assignment. The module
  imports only Frappe, so installing `ione_core` on a site without HRMS does not
  introduce an HRMS import requirement.
- The app declares Python >=3.14; the extension adds no package dependencies.
- The generator contract is a 90-day default horizon, seven active days per
  cycle, and frequencies Every Week / Every 2 Weeks / Every 3 Weeks / Every 4 Weeks.
  Changes to these upstream rules require renewed compatibility testing.
- Explicit end dates, including partial active weeks, retain the previous
  production fix's behavior. This extension does not add a new policy for
  maintaining an original cycle anchor across arbitrary manually split windows.

Reviewed official references:

| Component | Reference revision | Source file SHA-256 |
| --- | --- | --- |
| HRMS generator and scheduler | `7fc314bdbdb69d0161bff1ba4dd46f4a7dffd8a2` | `ad7d9b0781ef9cd253155a950d222ab617362c59d15da356206c654a34486bba` |
| Frappe cooperative extension loader | `a4a709126cbe7bfe1c57269f92694ca6eb80ce51` | `8664241930e2c3f61836be0af97b7d518b04e41dbcce6f8f8965a2682032863a` |

On 2026-10-22, the running Frappe checkout `81052d5e1c12` and HRMS checkout
`7fc314bdbdb6` were inspected directly: both relevant source files match the
reference hashes above. The extension module also matches the deployed file
byte for byte (SHA-256
`2b46edb4b3bafdd8485795dbb57f0fc1c33eb8f69200ac0928b491c9624dc15e`).
The table preserves the original reference revisions for reproducible tests;
validate the relevant source file again when upgrading either app.

## Tests

Basic cursor tests use Python's standard library and no installed Frappe or HRMS:

```powershell
python -m unittest ione_core.tests.test_hrms_shift_cycle_boundary -v
```

The optional compatibility tests use the actual official HRMS controller and
scheduler AST and Frappe extension-loader AST, with only document/schedule I/O
replaced by memory objects. They also compare against the previous one-line
progress-cursor fix. The 11 tests cover 24 fixed-origin two-batch scenarios,
72 explicit horizons, repeated batches, leap dates, empty schedules, native
errors, cursor persistence errors and another cooperative mixin. All identities
are synthetic; the tests contain no employee or attendance records.

Official source is deliberately not vendored into this MIT application. Obtain
these two files from the pinned upstream revisions into a separate directory,
preserving their exact original bytes and upstream licenses:

- Save [the HRMS controller](https://github.com/frappe/hrms/blob/7fc314bdbdb69d0161bff1ba4dd46f4a7dffd8a2/hrms/hr/doctype/shift_schedule_assignment/shift_schedule_assignment.py)
  as `reference-official-shift-schedule-assignment.py`.
- Save [the Frappe document module](https://github.com/frappe/frappe/blob/a4a709126cbe7bfe1c57269f92694ca6eb80ce51/frappe/model/document.py)
  as `reference-frappe-document.py`.

The tests never download files. A supplied reference must match its SHA-256 in
the table; missing or altered sources fail the explicitly enabled check. With
no reference directory configured, only this optional module is clearly marked
as skipped; the basic tests remain runnable.

```powershell
$env:IONE_HRMS_COMPAT_REFERENCE_DIR = "C:\path\to\official-references"
python -m unittest ione_core.tests.test_hrms_shift_cycle_boundary ione_core.tests.test_hrms_shift_cycle_compat -v
Remove-Item Env:IONE_HRMS_COMPAT_REFERENCE_DIR
```

These isolated checks do not exercise real Frappe metadata, permissions or
database transactions. Before upgrading the supported versions, inspect the
resolved controller MRO and test ordinary `frappe.get_doc` and scheduled
generation in a transaction-controlled test site. Check cursor progression and
generated dates before enabling the scheduler against live employee data.

See [Frappe's hook documentation](https://docs.frappe.io/framework/user/en/python-api/hooks#extend-doctype-class).
