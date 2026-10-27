# Meal population from Education

`ione_core.meal_population` is an internal helper for meal planning. It does not
register API endpoints or read data at import time. The caller must authorize its
operation and own the database transaction. These helpers do not commit.

## Current roster

Create the `Student.custom_student_batch` Link to `Student Batch Name` using
`STUDENT_BATCH_CUSTOM_FIELD` before regular use. Maintain the field in Education
after the one-time legacy migration. The regular read path never queries old
Student Group or Program Enrollment tables.

```python
from ione_core.meal_population import get_population_snapshot

snapshot = get_population_snapshot(
    company="Example School",
    meal_date="2026-10-26",
    academic_year="2026-2027",
    academic_term="Autumn",
)
```

The result contains `total`, `classes` (`student_batch`, `count`), `roster_hash`,
`as_of` (UTC), `basis`, `academic_year` and `academic_term`. It contains no student
names or student record identifiers. Save this snapshot with the weekly plan;
do not silently refresh approved procurement quantities when the roster changes.

Only enabled, non-alumni, non-cancelled students are counted. Joining date is
inclusive; leaving date is the first date no longer enrolled. Blank dates do not
invent a historical enrollment date. Batch start/end dates are inclusive. Each
meal date must belong to one valid academic year and term; pass the identifiers
explicitly when date ranges overlap. Company ownership is checked on academic
periods where set and is always required on batches.

Students explicitly assigned to another company's batch are excluded. Active
students with missing or invalid batch links, missing batch company, disabled
batches, or expired/not-yet-active assigned batches cause a validation error
instead of silently lowering the count. A zero roster also fails closed.

These are **expected enrolled counts**, not attendance or meal confirmation.
Actual meal adjustments and attendance need their own confirmed records. The
current Student link represents current membership, not historical transfers;
historical meal plans must retain their saved snapshots.

## One-time migration

```python
from ione_core.meal_population import migrate_legacy_student_batches

preview = migrate_legacy_student_batches(
    company="Example School",
    academic_year="2026-2027",
    academic_term="Autumn",
)  # dry_run=True; no writes, no locks
```

Migration is the only path that reads the legacy Student Group tables. It checks
unique current groups and students, active source links, orphan links, existing
field conflicts, period consistency, and one legacy group to one current batch.
Companies must be consistent for **each** group. A blank batch company can be
filled only when education links prove the company or the entire site has exactly
one company matching the requested company. Multi-company ambiguity fails.

After backup, review, field creation, and authorization, a System Manager may
call the same function with the literal boolean `dry_run=False`. Strings such as
`"false"`, integer `0`, and null are rejected. The write path locks current rows,
validates the entire source before the first write, fills only empty student
batch links and empty batch company fields, and uses a savepoint to roll back a
failed batch. An outer caller must commit or roll back. A second successful run
is idempotent and fills nothing. It never changes student names, enablement,
birth dates, or other identity data.

Tests use synthetic identifiers only:

```text
python -I ione_core/tests/test_meal_population.py
```
