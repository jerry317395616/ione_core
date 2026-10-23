"""Offline queue/worker contract tests. No SDK, network or Frappe DB access."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sdk = types.ModuleType("dingtalk_stream")
sdk.EventHandler = type("EventHandler", (), {})
sdk.AckMessage = types.SimpleNamespace(STATUS_OK=200, STATUS_SYSTEM_EXCEPTION=500)
control = types.ModuleType("stream_import_control")


class Gate:
    valid = True
    paused = False
    bench = "/offline/bench"
    site = "offline.invalid"

    def public(self):
        return {"configured": True, "valid": self.valid, "paused": self.paused, "target": "release"}


class Control:
    def __init__(self, *args):
        pass

    @asynccontextmanager
    async def dispatch(self):
        yield Gate()

    def snapshot(self):
        return Gate()


control.ImportControl = Control
spec = importlib.util.spec_from_file_location("stream_candidate", ROOT / "dingtalk_stream_service.py")
stream = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"dingtalk_stream": sdk, "stream_import_control": control}):
    spec.loader.exec_module(stream)

BASE = 1792625400000
DAY = "2026-10-22"


def row(event="event-a", user="synthetic-user", stamp=BASE, day=DAY, due=0, received=100):
    return event, user, stamp, day, due, received


def new_db(path=":memory:"):
    db = sqlite3.connect(path)
    stream.initialize_database(db)
    return db


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.db = new_db()

    def tearDown(self):
        self.db.close()

    def test_migration_preserves_all_50_done_rows_and_pending_seed(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute(stream.SCHEMA)
        for i in range(50):
            legacy.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?,?,?,?)", (str(i), "old", BASE, DAY, 0, 1, 2, 4, 1))
        legacy.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?,?,?,?)", ("pending", "old", BASE, DAY, 0, 1, None, 2, 0))
        legacy.commit()
        original = legacy.execute("SELECT * FROM inbox ORDER BY event_id").fetchall()
        stream.initialize_database(legacy)
        self.assertEqual(original, legacy.execute("SELECT event_id,user_id,check_time,day,next_try,received_at,imported_at,attempts,done FROM inbox ORDER BY event_id").fetchall())
        self.assertEqual(51, legacy.execute("SELECT COUNT(*) FROM inbox_times").fetchone()[0])
        stream.initialize_database(legacy)
        self.assertEqual(51, legacy.execute("SELECT COUNT(*) FROM inbox_times").fetchone()[0])
        stream.persist_rows(legacy, [row(event="0", user="old")])
        self.assertEqual((1, 0), legacy.execute("SELECT done,revision FROM inbox WHERE event_id='0'").fetchone())
        self.assertEqual([BASE], stream.next_batch(legacy, 1)["check_times"])
        legacy.close()

    def test_duplicate_is_noop_and_new_earlier_time_reopens(self):
        stream.persist_rows(self.db, [row()])
        batch = stream.next_batch(self.db, 1)
        stream.record_result(self.db, batch, True, 2)
        original = self.db.execute("SELECT revision,done,attempts FROM inbox").fetchone()
        stream.persist_rows(self.db, [row(received=200)])
        self.assertEqual(original, self.db.execute("SELECT revision,done,attempts FROM inbox").fetchone())
        stream.persist_rows(self.db, [row(stamp=BASE - 1000)])
        self.assertEqual((2, 0), self.db.execute("SELECT revision,done FROM inbox").fetchone())
        self.assertEqual([BASE - 1000, BASE], stream.next_batch(self.db, 1)["check_times"])

    def test_same_event_preserves_all_times(self):
        stream.persist_rows(self.db, [row(stamp=BASE + i * 1000) for i in range(5)])
        self.assertEqual(1, self.db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0])
        self.assertEqual([BASE + i * 1000 for i in range(5)], stream.next_batch(self.db, 1)["check_times"])

    def test_revision_race_preserves_new_time_while_import_running(self):
        stream.persist_rows(self.db, [row()])
        batch = stream.next_batch(self.db, 1)
        stream.record_attempt(self.db, batch, 2)
        stream.persist_rows(self.db, [row(stamp=BASE - 1000)])
        stream.record_result(self.db, batch, True, 3)
        self.assertEqual((0, None), self.db.execute("SELECT done,imported_at FROM inbox").fetchone())
        self.assertEqual([BASE - 1000, BASE], stream.next_batch(self.db, 4)["check_times"])

    def test_new_event_during_import_stays_pending(self):
        stream.persist_rows(self.db, [row()])
        batch = stream.next_batch(self.db, 1)
        stream.persist_rows(self.db, [row(event="new", stamp=BASE + 1000)])
        stream.record_result(self.db, batch, True, 2)
        self.assertEqual([(1,), (0,)], self.db.execute("SELECT done FROM inbox ORDER BY rowid").fetchall())

    def test_failed_old_revision_cannot_backoff_newer_work(self):
        stream.persist_rows(self.db, [row()])
        batch = stream.next_batch(self.db, 1)
        stream.persist_rows(self.db, [row(stamp=BASE - 1000)])
        stream.record_result(self.db, batch, False, 300)
        self.assertEqual((0, 0, 0, None), self.db.execute("SELECT done,attempts,next_try,last_failure_at FROM inbox").fetchone())

    def test_merge_due_same_employee_day_only(self):
        stream.persist_rows(self.db, [row(), row(event="second", stamp=BASE + 1000), row(event="duplicate-time"), row(event="future", due=100), row(event="other-person", user="other"), row(event="other-day", day="2026-10-21")])
        batch = stream.next_batch(self.db, 1)
        self.assertEqual(3, len(batch["rows"]))
        self.assertEqual([BASE, BASE + 1000], batch["check_times"])
        stream.record_result(self.db, batch, True, 2)
        self.assertEqual(3, self.db.execute("SELECT COUNT(*) FROM inbox WHERE done=0").fetchone()[0])

    def test_batch_bounds_and_large_single_event(self):
        stream.persist_rows(self.db, [row(stamp=BASE + i * 1000) for i in range(1000)])
        for i in range(300):
            stream.persist_rows(self.db, [row(event=f"extra-{i}", stamp=BASE + (1000 + i) * 1000)])
        first = stream.next_batch(self.db, 1)
        self.assertEqual(1000, len(first["check_times"]))
        self.assertEqual(1, len(first["rows"]))
        stream.record_result(self.db, first, True, 2)
        second = stream.next_batch(self.db, 3)
        self.assertEqual(256, len(second["rows"]))
        self.assertEqual(256, len(second["check_times"]))

    def test_oversized_same_event_rolls_back_and_keeps_previous(self):
        stream.persist_rows(self.db, [row()])
        with self.assertRaises(ValueError):
            stream.persist_rows(self.db, [row(stamp=BASE + i * 1000) for i in range(1, 1001)])
        self.assertEqual([(BASE,)], self.db.execute("SELECT check_time FROM inbox_times").fetchall())
        self.assertEqual(1, self.db.execute("SELECT revision FROM inbox").fetchone()[0])

    def test_failure_retry_backoff_and_attempt_times_are_durable(self):
        stream.persist_rows(self.db, [row()])
        for attempt in range(3):
            batch = stream.next_batch(self.db, 10000)
            stream.record_attempt(self.db, batch, 10 + attempt)
            stream.record_result(self.db, batch, False, 20 + attempt)
        self.assertEqual((0, 3, 142, 12, 22), self.db.execute("SELECT done,attempts,next_try,last_attempt_at,last_failure_at FROM inbox").fetchone())
        self.assertIsNone(stream.next_batch(self.db, 141))
        batch = stream.next_batch(self.db, 142)
        stream.record_result(self.db, batch, True, 150)
        self.assertEqual((1, 150), self.db.execute("SELECT done,imported_at FROM inbox").fetchone())

    def test_stop_restart_recovers_committed_unacknowledged_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            first = new_db(path)
            stream.persist_rows(first, [row(), row(stamp=BASE - 1000)])
            first.close()
            second = new_db(path)
            self.assertEqual([BASE - 1000, BASE], stream.next_batch(second, 1)["check_times"])
            stream.persist_rows(second, [row(), row(stamp=BASE - 1000)])
            self.assertEqual(2, second.execute("SELECT revision FROM inbox").fetchone()[0])
            second.close()

    def test_health_aggregate_only_and_failure_visible(self):
        stream.persist_rows(self.db, [row()])
        for i in range(3):
            batch = stream.next_batch(self.db, 1000)
            stream.record_attempt(self.db, batch, 200 + i)
            stream.record_result(self.db, batch, False, 200 + i)
        with tempfile.TemporaryDirectory() as directory, patch.object(stream.os, "fchmod", lambda *_: None, create=True), patch.object(stream.os, "O_NOFOLLOW", getattr(stream.os, "O_NOFOLLOW", 0), create=True):
            stream.write_health(Path(directory), self.db, types.SimpleNamespace(websocket=object()), {}, Control())
            value = json.loads((Path(directory) / "health.json").read_text())
        self.assertEqual((1, 1, 1, 1, 100, 202, 202), tuple(value[k] for k in ("pending", "pending_employee_days", "failed_pending", "attention_pending", "oldest_pending_received_at", "last_import_attempt", "last_import_failure")))
        self.assertNotIn("synthetic-user", json.dumps(value))
        self.assertNotIn("event-a", json.dumps(value))


class IngressTests(unittest.TestCase):
    def event(self, corp="pinned-org", records=None):
        return types.SimpleNamespace(headers=types.SimpleNamespace(event_type=stream.TOPIC, event_corp_id=corp, event_id="event-a"), data={"dataList": records or [{"userId": "synthetic-user", "checkTime": BASE}]})

    def test_company_pin_and_conflicting_company(self):
        self.assertEqual([], stream.event_rows(self.event("wrong-org"), "pinned-org"))
        with self.assertRaises(ValueError):
            stream.event_rows(self.event(records=[{"userId": "synthetic-user", "checkTime": BASE, "corpId": "wrong-org"}]), "pinned-org")

    def test_all_event_times_retained_after_parse(self):
        rows = stream.event_rows(self.event(records=[{"userId": "synthetic-user", "checkTime": BASE}, {"userId": "synthetic-user", "checkTime": BASE - 1000}]), "pinned-org")
        db = new_db()
        stream.persist_rows(db, rows)
        self.assertEqual(2, db.execute("SELECT COUNT(*) FROM inbox_times").fetchone()[0])
        db.close()

    def test_ack_failure_if_durable_storage_fails(self):
        db = new_db()
        db.close()
        handler = stream.InboxHandler(db, "pinned-org")
        with patch.object(stream, "status") as status:
            result = asyncio.run(handler.process(self.event()))
        self.assertEqual((500, "retry"), result)
        status.assert_called_once_with("event_not_persisted")

    def test_ack_only_after_commit(self):
        db = new_db()
        handler = stream.InboxHandler(db, "pinned-org")
        self.assertEqual((200, "OK"), asyncio.run(handler.process(self.event())))
        self.assertFalse(db.in_transaction)
        self.assertEqual(1, db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0])
        db.close()


class WorkerContractTests(unittest.TestCase):
    def execute_child(self, count, fail_call=None, imported=None):
        frappe = types.ModuleType("frappe")
        calls = []
        commits, rollbacks = [], []
        frappe.init = lambda **_: None
        frappe.connect = lambda: None
        frappe.set_user = lambda _: None
        frappe.destroy = lambda: None
        frappe.db = types.SimpleNamespace(commit=lambda: commits.append(1), rollback=lambda: rollbacks.append(1))
        frappe.local = types.SimpleNamespace(db=frappe.db)
        backend = types.ModuleType("ione_core.dingtalk_attendance")

        def trigger(user, day, stamp, check_times):
            self.assertEqual("synthetic-user", user)
            self.assertEqual(DAY, day)
            self.assertEqual(max(check_times), stamp)
            self.assertLessEqual(len(check_times), 256)
            calls.append(check_times)
            if fail_call == len(calls):
                raise RuntimeError("offline intentional partial failure")
            if imported is not None:
                imported.update(check_times)
            return {"ok": True}

        backend.sync_stream_trigger = trigger
        payload = {"employee_userid": "synthetic-user", "day": DAY, "check_times": [BASE + i * 1000 for i in range(count)]}
        modules = {"frappe": frappe, "ione_core": types.ModuleType("ione_core"), "ione_core.dingtalk_attendance": backend}
        with patch.dict(sys.modules, modules), patch.object(sys, "argv", ["worker", "/offline/bench", "offline.invalid"]), patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), patch("signal.signal"):
            try:
                exec(stream.WORKER_CODE, {})
            except RuntimeError:
                if fail_call is None:
                    raise
        return calls, commits, rollbacks

    def test_full_event_partitions_without_acknowledging_remainder(self):
        calls, commits, rollbacks = self.execute_child(1000)
        self.assertEqual([256, 256, 256, 232], [len(call) for call in calls])
        self.assertEqual(1000, len(set(sum(calls, []))))
        self.assertEqual(([1], []), (commits, rollbacks))

    def test_partial_chunk_failure_rolls_back_and_propagates(self):
        calls, commits, rollbacks = self.execute_child(600, fail_call=2)
        self.assertEqual(2, len(calls))
        self.assertEqual(([], [1]), (commits, rollbacks))

    def test_partial_success_retries_full_set_without_inventing_remainder(self):
        imported = set()
        self.execute_child(600, fail_call=2, imported=imported)
        self.assertEqual(256, len(imported))
        self.execute_child(600, imported=imported)
        self.assertEqual({BASE + i * 1000 for i in range(600)}, imported)

    def test_worker_coalesces_and_commits_only_verified_snapshot(self):
        db = new_db()
        stream.persist_rows(db, [row(), row(event="other", stamp=BASE + 1000)])
        stop = asyncio.Event()
        calls = []

        async def fake_import(options, user, day, check_times):
            calls.append((user, day, check_times))
            stream.persist_rows(db, [row(stamp=BASE - 1000)])
            stop.set()
            return True

        with patch.object(stream, "run_import", fake_import):
            asyncio.run(stream.worker(types.SimpleNamespace(bench="/offline", site="offline.invalid"), db, stop))
        self.assertEqual(1, len(calls))
        self.assertEqual([BASE, BASE + 1000], calls[0][2])
        self.assertEqual([(0,), (1,)], db.execute("SELECT done FROM inbox ORDER BY rowid").fetchall())
        db.close()

    def test_import_lease_includes_result_commit(self):
        db = new_db()
        stream.persist_rows(db, [row()])
        stop = asyncio.Event()
        boundaries = []

        class BoundaryControl(Control):
            @asynccontextmanager
            async def dispatch(self):
                yield Gate()
                boundaries.append((db.in_transaction, db.execute("SELECT done FROM inbox").fetchone()[0]))

        async def fake_import(*args):
            stop.set()
            return True

        with patch.object(stream, "ImportControl", BoundaryControl), patch.object(stream, "run_import", fake_import):
            asyncio.run(stream.worker(types.SimpleNamespace(bench="/offline", site="offline.invalid"), db, stop))
        self.assertEqual([(False, 1)], boundaries)
        db.close()

    def test_maintenance_pause_preserves_queue_without_dispatch(self):
        db = new_db()
        stream.persist_rows(db, [row()])
        stop = asyncio.Event()

        class PausedControl(Control):
            @asynccontextmanager
            async def dispatch(self):
                gate = Gate()
                gate.paused = True
                yield gate
                stop.set()

        async def forbidden_import(*args):
            self.fail("paused gate dispatched an import")

        with patch.object(stream, "ImportControl", PausedControl), patch.object(stream, "run_import", forbidden_import):
            asyncio.run(stream.worker(types.SimpleNamespace(bench="/offline", site="offline.invalid"), db, stop))
        self.assertEqual((0, None), db.execute("SELECT done,last_attempt_at FROM inbox").fetchone())
        db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
