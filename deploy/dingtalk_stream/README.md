# DingTalk attendance and HRMS integration

This optional integration imports verified DingTalk records into native HRMS
Employee Checkin. A separate Linux Stream collector durably queues attendance
events, then asks the site's existing importer to retrieve and verify each
employee/day. Events never directly create Attendance documents. HRMS processes
attendance only after the complete employee scope and an ended shift window
have been verified.

The collector acknowledges an event only after SQLite commits it. It retains
every expected punch time, deduplicates redelivery, retries failures, and avoids
marking a newer revision complete when an older import finishes. Late records
for already released attendance remain available for human review.

## Site configuration and explicit opt-in

Installing I-ONE Core does **not** enable scheduled attendance imports. Set
`dingtalk_attendance_scheduler_enabled` to `1` in the intended site's private
configuration after validating the prerequisites below. Both scheduled wrappers
return `scheduler_disabled` otherwise. When enabled, missing source credentials
or other import errors remain failed jobs; they are not hidden. Manual methods
and Stream imports do not use this scheduler switch. Stop/pause the collector
separately when maintenance requires all imports to stop.

The organization-wide mapping/status and manual import endpoints are integration
administration operations, restricted to `Administrator` or `System Manager`.
This publication intentionally tightens the earlier I-ONE/HR role access; ordinary
AI or HR roles do not authorize bypassing Employee row permissions. The native
check-in list's separate read-only status/context endpoints retain their HR and
document-permission checks. Internal scheduler and Stream workers are unchanged.

The hooks are:

| Hook | Entry point |
| --- | --- |
| Daily cron `0 18 * * *` | `ione_core.dingtalk_schedule.run_daily` |
| Safety net cron `5-59/10 * * * *` | `ione_core.dingtalk_schedule.run_catchup` |
| Employee Checkin list | `public/js/dingtalk_employee_checkin_list.js` |

Relevant private site settings:

| Setting | Purpose |
| --- | --- |
| `dingtalk_attendance_scheduler_enabled` | Explicit scheduler opt-in; default disabled. |
| `dingtalk_cli_path` | Absolute path to the authenticated `dws` CLI. Otherwise searches `PATH`, then the service user's `~/.local/bin/dws`. |
| `dingtalk_attendance_profile` | Pin the CLI account/organization profile; use an explicitly verified profile in production. |
| `dingtalk_app_key`, `dingtalk_app_secret` | Optional API credentials instead of CLI authorization. Never commit their values. |
| `dingtalk_attendance_shift_types` | Explicit list of native Shift Type names to settle. An empty list imports check-ins without releasing shifts. |
| `dingtalk_employee_map` | Optional source-user-ID to Employee-ID mapping; prefer the Employee field and keep actual mappings private. |
| `dingtalk_stream_health_path` | Absolute path to this site's collector `health.json`; unset means unavailable. No machine-wide default is used. |
| `dingtalk_attendance_notify_users` | Optional existing site users receiving internal sync summaries; empty by default. |

The importer accepts matching uppercase environment settings as fallbacks for
its data-source options. The scheduler opt-in and health path are site settings,
so another site cannot inherit them accidentally from a shared process.

Before enabling: install HRMS, create/verify the Employee DingTalk mapping field
(`ensure_dingtalk_employee_field` is an explicit setup helper), map active
employees uniquely, and configure native assignments and shifts. Managed shifts
require auto-attendance enabled, native clock-driven watermark advancement
disabled, an attendance start date, and at least one absent-buffer day. Overnight
check-in windows are rejected. Missing/duplicate mappings block settlement.
The current employee query is bounded at 500; larger deployments need a separate
scope/pagination review before enabling this implementation.

The existing daily verification path requires the strict `dws attendance
+check-record` response contract (full batch coverage and original user IDs).
The optional app-credential API path can import check-ins but currently does not
provide that completeness proof; it therefore cannot release automatic
attendance. Do not bypass this guard to make a job appear successful.

This implementation retains the deployed China-time business rules:
`Asia/Shanghai`, an 18:00 settlement threshold, and same-day shift windows.
The site timezone, collector environment and Frappe process timezone must agree.
It is not a generic cross-timezone attendance adapter.

## Collector deployment

The collector requires Linux/POSIX locks and an independent Python virtualenv.
The tested SDK contract is `dingtalk-stream==0.24.4b1` (upstream commit
`8d8bb1c630848fee1ae8c7bdd11bc1b78097b611`) and requires asynchronous `stop()`.
Install `requirements.txt` in that virtualenv, not the Frappe bench environment.
Keep `dingtalk_stream_service.py` and `stream_import_control.py` together.

Use the bench operating-system account for the service. Its import subprocess
uses the selected bench's `env/bin/python` and the native Frappe `Administrator`
service identity, so this is a trusted server component with attendance write
access. The separate Stream credential JSON contains nonempty `client_id`,
`client_secret`, and the explicitly verified organization's `corp_id`. Supply
that file privately, owned by the service account with mode `0600`; never place
real credentials, employee IDs, event bodies or inbox databases in Git.

`service.env.example` and `dingtalk-attendance-stream.service` are templates.
Replace their paths, site and operating-system user, create the private state
directory with mode `0700`, and provide the environment file privately. Pin the
Stream subscription to `attendance_check_record` in the same authorized DingTalk
organization. This package does not provision or publish an application there.

The collector now requires explicit `--credentials`, `--bench` and `--site`.
`--state-dir` defaults to `/var/lib/dingtalk-attendance-stream`; give every
collector/site its own state directory and health path. Never share an inbox
across different organizations or sites. A per-state-directory process lock
prevents duplicate collectors. Existing inbox migrations are additive.

## Maintenance gate and release changes

`--import-control` enables an owner-only pause/drain gate. If it is configured but
missing, corrupt, unsafe or references an untrusted target, imports pause while
collection continues. The control directory must be a real absolute path owned
by the service account with mode `0700`; control/lock files must be regular,
single-link files with mode `0600`. Symlinked parent paths are rejected.

The trusted site and bench allowlist come from process startup, **never** from
the mutable control JSON. `--bench` is trusted automatically by the collector;
repeat `--allowed-bench` for any additional release targets. Configure those
targets in the service before switching. The control CLI requires the same
allowlist explicitly. For example, run as the service account (all values below
are illustrative):

```sh
python stream_import_control.py \
  --control /var/lib/dingtalk-attendance-stream/control/import-control.json \
  --site attendance.example.test \
  --allowed-bench /srv/frappe/bench \
  --allowed-bench /srv/frappe/releases/next \
  --bench /srv/frappe/bench --pause yes
```

Create the `control` directory privately before initializing the gate with this
command. Use `--pause no` to resume, with the selected trusted `--bench`. Use the
same CLI to initialize or repair a control file; do not hand-edit JSON when
maintenance requires drain proof.

A successful `drained: true` covers both subprocess exit and durable inbox result
commit. A timeout leaves the gate paused and is **not** proof that an in-flight
import has stopped. This gate drains the Stream worker only: scheduled/manual
imports and other writers must also be stopped/drained before site maintenance.
Health output contains only aggregates, generic target labels and a generation
ID, not employee identifiers, credential text or full filesystem paths.

## Verification without a site

From the repository root, the following tests use synthetic data and mocks only:

```sh
python -m unittest ione_core.tests.test_dingtalk_attendance \
  ione_core.tests.test_dingtalk_realtime ione_core.tests.test_dingtalk_schedule
node ione_core/tests/test_dingtalk_employee_checkin_list.cjs
python -m unittest discover -s deploy/dingtalk_stream/tests -v
```

Run the last command on Linux to exercise real POSIX ownership, file modes,
symlink rejection and pause/drain locks. Those control tests skip on other
platforms; portable queue tests mock the gate. No test needs SDK credentials,
employee records, a database server or a network connection.

The list regression includes Frappe/jQuery-style thenables without `.finally`,
transient context failure recovery, permission-filtered record enrichment,
existing native actions/indicators, and selected-row preservation. Backend tests
cover full-scope settlement, late-shift deferral, watermarks and late-record
review. Stream tests cover durability, all expected times, bounded batching,
revision races, retries, shutdown, maintenance drain and redacted health data.

These offline checks do not replace an approved deployment rehearsal against the
target Frappe/HRMS versions and a separate authorized DingTalk test organization.
