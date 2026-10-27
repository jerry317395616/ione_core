"""Offline tests: temporary SQLite, fake SDK/child, no real state or network."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

if sys.platform != "linux":
    raise unittest.SkipTest("Import-control ownership, mode and flock tests require Linux")

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("stream_import_control", ROOT / "stream_import_control.py")
control = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"stream_import_control": control}):
    spec.loader.exec_module(control)

OLD_BENCH = "/srv/frappe/bench"
RELEASE_BENCH = "/srv/frappe/releases/test-release"
SITE = "attendance.example.test"
ALLOWED_BENCHES = (OLD_BENCH, RELEASE_BENCH)


def publish_control(path, paused, bench, timeout=300):
    return control.set_control(path, paused, bench, timeout, site=SITE, allowed_benches=ALLOWED_BENCHES)

sdk = types.ModuleType("dingtalk_stream")
sdk.EventHandler = object
class Ack:
    STATUS_OK = 200
    STATUS_SYSTEM_EXCEPTION = 500
    def __init__(self):
        self.headers = types.SimpleNamespace()
sdk.AckMessage = Ack
spec = importlib.util.spec_from_file_location("candidate_service", ROOT / "dingtalk_stream_service.py")
service = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"dingtalk_stream": sdk, "stream_import_control": control}):
    spec.loader.exec_module(service)


def event(event_id="synthetic-event", stamp=1792638000000):
    return types.SimpleNamespace(data={"corpId": "synthetic-corp", "userId": "synthetic-user", "checkTime": stamp},
        headers=types.SimpleNamespace(event_type=service.TOPIC, event_corp_id="synthetic-corp", event_id=event_id, message_id="synthetic-message"))


async def until(predicate, timeout=4):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for test condition")
        await asyncio.sleep(0.01)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stream-gate-offline-")
        self.folder = Path(self.temp.name)
        self.folder.chmod(0o700)
        self.path = self.folder / "import-control.json"
        self.gate = control.ImportControl(self.path, OLD_BENCH, SITE, ALLOWED_BENCHES)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, paused=False, bench=OLD_BENCH):
        return publish_control(self.path, paused, bench)

    def test_unconfigured_defaults_exact(self):
        gate = control.ImportControl(None, "/srv/custom-prior-cli-bench", "prior-site")
        self.assertEqual((gate.snapshot().configured, gate.snapshot().paused, gate.snapshot().bench, gate.snapshot().site), (False, False, "/srv/custom-prior-cli-bench", "prior-site"))

    def test_target_policy_requires_explicit_site_and_absolute_allowlist(self):
        for site, benches in (("", {OLD_BENCH}), (SITE, set()), (SITE, {"relative"}), (SITE, {"/srv/../untrusted"})):
            with self.subTest(site=site, benches=benches):
                with self.assertRaises(control.UnsafeControl):
                    control.TargetPolicy(site, frozenset(benches))

    def test_unlisted_release_cannot_authorize_itself_in_control_json(self):
        self.publish(bench=RELEASE_BENCH)
        primary_only = control.ImportControl(self.path, OLD_BENCH, SITE)
        self.assertFalse(primary_only.snapshot().valid)
        self.assertTrue(primary_only.snapshot().paused)

    def test_missing_file_closed(self):
        self.assertTrue(self.gate.snapshot().paused)
        self.assertFalse(self.gate.snapshot().valid)

    def test_roundtrip_pause_resume_targets(self):
        for paused, bench in ((True, OLD_BENCH), (False, OLD_BENCH), (True, RELEASE_BENCH), (False, RELEASE_BENCH), (False, OLD_BENCH)):
            result = self.publish(paused, bench)
            value = self.gate.snapshot()
            self.assertTrue(result["drained"])
            self.assertEqual((value.valid, value.paused, value.bench, value.site), (True, paused, bench, SITE))
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_target_closed(self):
        self.publish()
        data = json.loads(self.path.read_text())
        for bench, site in (("/tmp/untrusted", SITE), (OLD_BENCH + "/../native-bench", SITE), (OLD_BENCH, "other-site")):
            data.update(bench=bench, site=site)
            self.path.write_text(json.dumps(data))
            self.assertFalse(self.gate.snapshot().valid)
        with self.assertRaises(ValueError):
            self.publish(bench="/tmp/untrusted")

    def test_permission_rejected(self):
        self.publish()
        self.path.chmod(0o640)
        self.assertFalse(self.gate.snapshot().valid)
        self.path.chmod(0o600)
        self.folder.chmod(0o750)
        self.assertFalse(self.gate.snapshot().valid)

    def test_symlink_and_hardlink_rejected(self):
        self.publish()
        original = self.folder / "original.json"
        self.path.rename(original)
        self.path.symlink_to(original)
        self.assertFalse(self.gate.snapshot().valid)
        self.path.unlink()
        os.link(original, self.path)
        self.assertFalse(self.gate.snapshot().valid)

    def test_corruption_schema_oversize_closed(self):
        self.publish()
        for data in ("{", "[]", "null", "x" * 4097, json.dumps({"version": True}), json.dumps({"version": 1, "pause_import": 1, "bench": OLD_BENCH, "site": SITE, "generation": "a" * 32})):
            self.path.write_text(data)
            self.assertFalse(self.gate.snapshot().valid)

    def test_lock_permission_closed(self):
        self.publish()
        path = self.folder / "import-control.json.dispatch.lock"
        path.chmod(0o644)
        async def probe():
            async with self.gate.dispatch() as decision:
                self.assertTrue(decision.paused)
                self.assertFalse(decision.valid)
        asyncio.run(probe())

    def test_atomic_control_temp_cleanup(self):
        for _ in range(5):
            self.publish()
        self.assertFalse(list(self.folder.glob("*.tmp")))


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stream-worker-offline-")
        self.folder = Path(self.temp.name)
        self.folder.chmod(0o700)
        self.path = self.folder / "import-control.json"
        self.gate = control.ImportControl(self.path, OLD_BENCH, SITE, ALLOWED_BENCHES)
        self.db = sqlite3.connect(self.folder / "synthetic-inbox.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        service.initialize_database(self.db)
        self.handler = service.InboxHandler(self.db, "synthetic-corp")
        self.stop = asyncio.Event()
        self.options = types.SimpleNamespace(bench=OLD_BENCH, site=SITE, import_control=str(self.path), allowed_bench=ALLOWED_BENCHES)
        self.runtime = {}
        self.tasks = []

    async def asyncTearDown(self):
        self.stop.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 5)
        self.db.close()
        self.temp.cleanup()

    def start_worker(self):
        task = asyncio.create_task(service.worker(self.options, self.db, self.stop, self.runtime))
        self.tasks.append(task)
        return task

    async def add(self, event_id="synthetic-event", stamp=1792638000000):
        result = await self.handler.process(event(event_id, stamp))
        self.assertEqual(result, (Ack.STATUS_OK, "OK"))
        with self.db:
            self.db.execute("UPDATE inbox SET next_try=0")

    def done(self):
        return self.db.execute("SELECT COUNT(*) FROM inbox WHERE done=1").fetchone()[0]

    async def test_paused_collects_durably_and_no_import(self):
        publish_control(self.path, True, OLD_BENCH)
        calls = []
        async def fake_import(*args):
            calls.append(args)
            return True
        with patch.object(service, "run_import", fake_import):
            self.start_worker()
            await self.add()
            await asyncio.sleep(0.1)
            self.assertEqual(calls, [])
            self.assertEqual(self.done(), 0)
            other = sqlite3.connect(self.folder / "synthetic-inbox.sqlite3")
            self.assertEqual(other.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 1)
            other.close()

    async def test_resume_and_target_switch_back(self):
        calls = []
        async def fake_import(options, *_):
            calls.append((options.bench, options.site))
            return True
        with patch.object(service, "run_import", fake_import):
            publish_control(self.path, False, OLD_BENCH)
            await self.add("one")
            self.start_worker()
            await until(lambda: self.done() == 1)
            await asyncio.to_thread(publish_control, self.path, True, OLD_BENCH)
            await self.add("two")
            await asyncio.to_thread(publish_control, self.path, False, RELEASE_BENCH)
            await until(lambda: self.done() == 2)
            await asyncio.to_thread(publish_control, self.path, True, RELEASE_BENCH)
            await self.add("three")
            await asyncio.to_thread(publish_control, self.path, False, OLD_BENCH)
            await until(lambda: self.done() == 3)
        self.assertEqual(calls, [(OLD_BENCH, SITE), (RELEASE_BENCH, SITE), (OLD_BENCH, SITE)])

    async def test_import_failure_not_done(self):
        publish_control(self.path, False, OLD_BENCH)
        await self.add()
        async def failed(*_):
            return False
        with patch.object(service, "run_import", failed):
            self.start_worker()
            await until(lambda: self.db.execute("SELECT attempts FROM inbox").fetchone()[0] == 1)
            self.assertEqual(self.done(), 0)
            self.assertIsNone(self.db.execute("SELECT imported_at FROM inbox").fetchone()[0])

    async def test_exception_not_done(self):
        publish_control(self.path, False, OLD_BENCH)
        await self.add()
        async def failed(*_):
            raise RuntimeError("synthetic")
        with patch.object(service, "run_import", failed):
            self.start_worker()
            await until(lambda: self.db.execute("SELECT attempts FROM inbox").fetchone()[0] == 1)
            self.assertEqual(self.done(), 0)

    async def test_duplicate_ack_and_newer_same_key_not_marked_done(self):
        publish_control(self.path, False, OLD_BENCH)
        await self.add()
        await self.add()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 1)
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(*_):
            entered.set()
            await release.wait()
            self.stop.set()
            return True
        with patch.object(service, "run_import", delayed):
            self.start_worker()
            await entered.wait()
            await self.add(stamp=1792638001000)
            release.set()
            await self.tasks[0]
        self.assertEqual(self.done(), 0)
        self.assertEqual(self.db.execute("SELECT check_time,attempts FROM inbox").fetchone(), (1792638001000, 0))

    async def test_pause_waits_inflight_and_collector_stays_live(self):
        publish_control(self.path, False, OLD_BENCH)
        await self.add("one")
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def delayed(options, *_):
            calls.append(options.bench)
            entered.set()
            await release.wait()
            return True
        with patch.object(service, "run_import", delayed):
            self.start_worker()
            await entered.wait()
            draining = asyncio.create_task(asyncio.to_thread(publish_control, self.path, True, OLD_BENCH, 4))
            await until(lambda: self.gate.snapshot().paused)
            self.assertTrue(self.runtime["inflight"])
            self.assertFalse(draining.done())
            await self.add("two")
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 2)
            release.set()
            receipt = await draining
            self.assertTrue(receipt["drained"])
            self.assertFalse(self.runtime["inflight"])
            self.assertEqual(self.done(), 1)
            await asyncio.sleep(0.1)
            self.assertEqual(len(calls), 1)

    async def test_drain_timeout_leaves_paused(self):
        publish_control(self.path, False, OLD_BENCH)
        async with self.gate.dispatch() as decision:
            self.assertFalse(decision.paused)
            with self.assertRaises(TimeoutError):
                await asyncio.to_thread(publish_control, self.path, False, RELEASE_BENCH, 0.1)
        self.assertTrue(self.gate.snapshot().paused)

    async def test_invalid_gate_prevents_dispatch(self):
        await self.add()
        calls = []
        async def fake(*args):
            calls.append(args)
        with patch.object(service, "run_import", fake):
            self.start_worker()
            await asyncio.sleep(0.1)
            self.assertEqual(calls, [])
            self.assertEqual(self.done(), 0)

    async def test_health_exposes_no_identity(self):
        publish_control(self.path, True, RELEASE_BENCH)
        await self.add()
        client = types.SimpleNamespace(websocket=object())
        service.write_health(self.folder, self.db, client, {"inflight": True, "inflight_target": "old", "inflight_started_at": 123}, self.gate)
        value = json.loads((self.folder / "health.json").read_text())
        self.assertTrue(value["import_inflight"])
        self.assertTrue(value["import_control"]["paused"])
        self.assertEqual(value["import_control"]["target"], "configured")
        self.assertNotIn("synthetic-user", json.dumps(value))
        self.assertNotIn("synthetic-event", json.dumps(value))

    async def test_no_control_keeps_prior_dispatch(self):
        self.options.import_control = None
        await self.add()
        calls = []
        async def fake(options, *_):
            calls.append((options.bench, options.site))
            return True
        with patch.object(service, "run_import", fake):
            self.start_worker()
            await until(lambda: self.done() == 1)
        self.assertEqual(calls, [(OLD_BENCH, SITE)])

    async def test_import_subprocess_cwd_uses_sites(self):
        options = types.SimpleNamespace(bench=RELEASE_BENCH, site=SITE)
        calls = []
        class Child:
            returncode = 0
            async def communicate(self, payload):
                self.payload = json.loads(payload)
        child = Child()
        async def spawn(*args, **kwargs):
            calls.append((args, kwargs))
            return child
        with patch.object(asyncio, "create_subprocess_exec", spawn):
            self.assertTrue(await service.run_import(options, "synthetic-user", "2026-10-22", [1792638000000]))
        self.assertEqual(calls[0][1]["cwd"], RELEASE_BENCH + "/sites")
        self.assertEqual(calls[0][0][0], RELEASE_BENCH + "/env/bin/python")

    async def test_import_subprocess_timeout_terminates_then_kills(self):
        options = types.SimpleNamespace(bench=OLD_BENCH, site=SITE)
        calls = []
        class Child:
            returncode = None
            async def communicate(self, _):
                calls.append("communicate")
            def terminate(self):
                calls.append("terminate")
            def kill(self):
                calls.append("kill")
                self.returncode = -9
            async def wait(self):
                calls.append("wait")
        child = Child()
        async def spawn(*args, **kwargs):
            return child
        async def timed_out(awaitable, timeout):
            await awaitable
            raise asyncio.TimeoutError()
        with patch.object(asyncio, "create_subprocess_exec", spawn), patch.object(asyncio, "wait_for", timed_out):
            with self.assertRaises(asyncio.TimeoutError):
                await service.run_import(options, "synthetic-user", "2026-10-22", [1792638000000])
        self.assertEqual(calls, ["communicate", "terminate", "wait", "kill", "wait"])

    async def test_persistence_failure_requests_redelivery(self):
        broken = sqlite3.connect(":memory:")
        handler = service.InboxHandler(broken, "synthetic-corp")
        try:
            with patch.object(service, "status"):
                result = await handler.process(event())
            self.assertEqual(result, (Ack.STATUS_SYSTEM_EXCEPTION, "retry"))
        finally:
            broken.close()

    async def test_raw_ack_does_not_echo_payload(self):
        response = await self.handler.raw_process(event())
        self.assertEqual(response.code, Ack.STATUS_OK)
        self.assertEqual(response.data, {})
        self.assertEqual(response.headers.message_id, "synthetic-message")


if __name__ == "__main__":
    unittest.main(verbosity=2)
