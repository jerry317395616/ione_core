#!/usr/bin/env python3
"""Durable attendance Stream ingress; no direct attendance writes.

SDK API reviewed at open-dingtalk/dingtalk-stream-sdk-python commit
8d8bb1c630848fee1ae8c7bdd11bc1b78097b611 (0.24.4b1); requires async stop().
Credentials: separate, owner-only JSON with client_id, client_secret, corp_id.
The bench sync_stream_trigger must raise on transient/partial import failures;
successful returns must mean the requested employee/day was durably processed.
"""
import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import stat
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from stream_import_control import ImportControl

# SDK and transport diagnostics can contain tickets, secrets or full events.
logging.disable(logging.CRITICAL)
import dingtalk_stream as sdk

TOPIC = "attendance_check_record"
SCHEMA = "CREATE TABLE IF NOT EXISTS inbox(event_id TEXT,user_id TEXT,check_time INTEGER,day TEXT,next_try REAL,received_at REAL,imported_at REAL,attempts INTEGER NOT NULL DEFAULT 0,done INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(event_id,user_id,day))"
MAX_BATCH_EVENTS = 256
MAX_BATCH_TIMES = 1000
WORKER_CODE = """
import json, signal, sys
import frappe
from ione_core.dingtalk_attendance import sync_stream_trigger
def terminate_import(_signum, _frame):
    raise TimeoutError('attendance import terminated')
signal.signal(signal.SIGTERM, terminate_import)
args = json.load(sys.stdin)
frappe.init(site=sys.argv[2], sites_path=sys.argv[1] + '/sites')
try:
    frappe.connect()
    frappe.set_user('Administrator')
    # A legal event can contain up to 1000 punches. The verified backend accepts
    # 256 expected times per lookup; do not acknowledge an unverified remainder.
    stamps = args['check_times']
    for offset in range(0, len(stamps), 256):
        chunk = stamps[offset:offset + 256]
        result = sync_stream_trigger(args['employee_userid'], args['day'], max(chunk), check_times=chunk)
        if not isinstance(result, dict) or result.get('ok') is not True or result.get('errors'):
            raise RuntimeError('sync did not complete')
    frappe.db.commit()
except BaseException:
    if getattr(frappe.local, 'db', None):
        frappe.db.rollback()
    raise
finally:
    frappe.destroy()
"""


def status(code, **counts):
    print(json.dumps({"time": int(time.time()), "status": code, **counts}), flush=True)


def initialize_database(db):
    """Additive, restart-safe migration of the existing owner-only inbox."""
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    with db:
        db.execute(SCHEMA)
        columns = {row[1] for row in db.execute("PRAGMA table_info(inbox)")}
        for name, declaration in (
            ("revision", "INTEGER NOT NULL DEFAULT 0"),
            ("first_received_at", "REAL"),
            ("last_attempt_at", "REAL"),
            ("last_failure_at", "REAL"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE inbox ADD COLUMN {name} {declaration}")
        db.execute("UPDATE inbox SET first_received_at=received_at WHERE first_received_at IS NULL")
        db.execute("CREATE TABLE IF NOT EXISTS inbox_times(event_id TEXT,user_id TEXT,day TEXT,check_time INTEGER,PRIMARY KEY(event_id,user_id,day,check_time))")
        # Existing rows retain their status. Seed completed identities too, so
        # redelivery of an old event cannot reopen it merely after migration.
        db.execute("INSERT OR IGNORE INTO inbox_times SELECT event_id,user_id,day,check_time FROM inbox")
        db.execute("CREATE INDEX IF NOT EXISTS pending ON inbox(done,next_try)")


def persist_rows(db, rows):
    """Commit every distinct expected time before acknowledging its event."""
    with db:
        for event_id, user, stamp, day, next_try, received in rows:
            inserted = db.execute("INSERT OR IGNORE INTO inbox_times VALUES(?,?,?,?)", (event_id, user, day, stamp)).rowcount
            if inserted and db.execute("SELECT COUNT(*) FROM inbox_times WHERE event_id=? AND user_id=? AND day=?", (event_id, user, day)).fetchone()[0] > MAX_BATCH_TIMES:
                raise ValueError("too many times for one attendance event")
            db.execute("""INSERT INTO inbox(event_id,user_id,check_time,day,next_try,received_at,first_received_at,revision)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(event_id,user_id,day) DO UPDATE SET
                check_time=MAX(inbox.check_time,excluded.check_time),received_at=excluded.received_at,
                next_try=CASE WHEN ? THEN excluded.next_try ELSE inbox.next_try END,
                attempts=CASE WHEN ? THEN 0 ELSE inbox.attempts END,
                done=CASE WHEN ? THEN 0 ELSE inbox.done END,
                revision=inbox.revision+?""",
                (event_id, user, stamp, day, next_try, received, received, int(bool(inserted)), inserted, inserted, inserted, inserted))


def next_batch(db, now):
    """Coalesce only due work for one employee/day, retaining each revision."""
    first = db.execute("SELECT user_id,day FROM inbox WHERE done=0 AND next_try<=? ORDER BY next_try,rowid LIMIT 1", (now,)).fetchone()
    if first is None:
        return None
    candidates = db.execute("SELECT rowid,event_id,user_id,day,attempts,check_time,revision FROM inbox WHERE done=0 AND next_try<=? AND user_id=? AND day=? ORDER BY next_try,rowid LIMIT ?", (now, *first, MAX_BATCH_EVENTS)).fetchall()
    rows, stamps = [], set()
    for row in candidates:
        expected = {value[0] for value in db.execute("SELECT check_time FROM inbox_times WHERE event_id=? AND user_id=? AND day=? LIMIT ?", (row[1], row[2], row[3], MAX_BATCH_TIMES + 1))}
        expected.add(row[5])
        if len(expected) > MAX_BATCH_TIMES:
            raise ValueError("attendance event exceeds verification batch bound")
        if rows and len(stamps | expected) > MAX_BATCH_TIMES:
            break
        rows.append(row)
        stamps.update(expected)
    return {"user": first[0], "day": first[1], "rows": rows, "check_times": sorted(stamps)}


def record_attempt(db, batch, now):
    with db:
        db.executemany("UPDATE inbox SET last_attempt_at=? WHERE rowid=? AND revision=?", [(now, row[0], row[6]) for row in batch["rows"]])


def record_result(db, batch, success, now):
    with db:
        for row in batch["rows"]:
            if success:
                db.execute("UPDATE inbox SET done=1,imported_at=? WHERE rowid=? AND revision=?", (now, row[0], row[6]))
            else:
                delay = min(3600, 30 * 2 ** min(row[4], 7))
                db.execute("UPDATE inbox SET attempts=attempts+1,next_try=?,last_failure_at=? WHERE rowid=? AND revision=?", (now + delay, now, row[0], row[6]))


def credentials(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            raise ValueError("credential file must be owned by service user with mode 0600")
        value = json.load(handle)
    if any(not isinstance(value.get(k), str) or not value[k].strip() for k in ("client_id", "client_secret", "corp_id")):
        raise ValueError("credential fields missing")
    return value


def event_rows(event, corp_id):
    data, headers = event.data, event.headers
    if headers.event_type and headers.event_type != TOPIC:
        return []
    if not isinstance(data, dict):
        raise ValueError("invalid event body")
    kind = headers.event_type or data.get("EventType") or data.get("eventType")
    if kind != TOPIC:
        return []
    corps = [x for x in (headers.event_corp_id, data.get("eventCorpId"), data.get("CorpId"), data.get("corpId")) if x]
    if not corps or any(x != corp_id for x in corps):
        return []
    event_id = headers.event_id or data.get("eventId")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 256:
        raise ValueError("missing event identifier")
    body = data.get("data", data)
    if not isinstance(body, dict):
        raise ValueError("invalid event data")
    records = body.get("dataList", body.get("DataList", [body] if "userId" in body else None))
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        raise ValueError("invalid attendance records")
    rows = []
    for item in records:
        if not isinstance(item, dict) or item.get("corpId", corp_id) != corp_id:
            raise ValueError("invalid record company")
        user, stamp = item.get("userId"), item.get("checkTime")
        if not isinstance(user, str) or not 1 <= len(user) <= 256 or isinstance(stamp, bool):
            raise ValueError("invalid record identity")
        stamp = int(stamp)
        if not 946684800000 <= stamp <= 4102444800000:
            raise ValueError("invalid millisecond check time")
        day = datetime.fromtimestamp(stamp / 1000, ZoneInfo("Asia/Shanghai")).date().isoformat()
        now = time.time()
        rows.append((event_id, user, stamp, day, now + 15, now))
    return rows


class InboxHandler(sdk.EventHandler):
    def __init__(self, db, corp_id):
        super().__init__()
        self.db, self.corp_id = db, corp_id

    async def process(self, event):
        try:
            rows = event_rows(event, self.corp_id)
            persist_rows(self.db, rows)
            return sdk.AckMessage.STATUS_OK, "OK"
        except Exception:
            status("event_not_persisted")
            return sdk.AckMessage.STATUS_SYSTEM_EXCEPTION, "retry"

    async def raw_process(self, event):
        # Do not use SDK's default event ACK, which echoes the complete payload.
        ack = sdk.AckMessage()
        ack.code, ack.message = await self.process(event)
        ack.headers.message_id = event.headers.message_id
        ack.headers.content_type = "application/json"
        ack.data = {}
        return ack


async def run_import(options, user, day, check_times):
    child = await asyncio.create_subprocess_exec(str(Path(options.bench) / "env/bin/python"), "-c", WORKER_CODE,
        options.bench, options.site, cwd=str(Path(options.bench) / "sites"), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        payload = json.dumps({"employee_userid": user, "day": day, "check_times": check_times}).encode()
        await asyncio.wait_for(child.communicate(payload), timeout=240)
        return child.returncode == 0
    finally:
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), timeout=10)
            except asyncio.TimeoutError:
                child.kill()
                await child.wait()


async def worker(options, db, stop, runtime=None):
    runtime = runtime if runtime is not None else {"inflight": False}
    control = ImportControl(getattr(options, "import_control", None), options.bench, options.site,
        getattr(options, "allowed_bench", ()))
    while not stop.is_set():
        dispatched = False
        # The shared lease covers the child AND its inbox result commit. A control
        # update first publishes pause, then waits for this exact boundary.
        async with control.dispatch() as gate:
            runtime["control"] = gate.public()
            batch = None
            if gate.valid and not gate.paused:
                batch = next_batch(db, time.time())
            if batch and not stop.is_set():
                dispatched = True
                runtime.update(inflight=True, inflight_target=gate.public()["target"], inflight_started_at=time.time())
                target = SimpleNamespace(bench=gate.bench, site=gate.site)
                try:
                    record_attempt(db, batch, time.time())
                    try:
                        success = await run_import(target, batch["user"], batch["day"], batch["check_times"])
                    except Exception:
                        success = False
                    record_result(db, batch, success, time.time())
                finally:
                    runtime.update(inflight=False, inflight_target=None, inflight_started_at=None)
        if not dispatched:
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
        else:
            # Let collection/health progress even under a perpetually full inbox.
            await asyncio.sleep(0)


def write_health(state, db, client, runtime=None, control=None):
    pending, received, imported, oldest, failed, attention, attempted, failure = db.execute("""SELECT
        SUM(done=0),MAX(received_at),MAX(imported_at),
        MIN(CASE WHEN done=0 THEN first_received_at END),
        SUM(done=0 AND attempts>0),SUM(done=0 AND attempts>=3),
        MAX(last_attempt_at),MAX(last_failure_at) FROM inbox""").fetchone()
    pending_groups = db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM inbox WHERE done=0 GROUP BY user_id,day)").fetchone()[0]
    value = {"updated_at": time.time(), "connected": client.websocket is not None,
             "pending": pending or 0, "pending_employee_days": pending_groups,
             "oldest_pending_received_at": oldest, "failed_pending": failed or 0,
             "attention_pending": attention or 0,
             "last_event_received": received, "last_import_success": imported,
             "last_import_attempt": attempted, "last_import_failure": failure}
    if control is not None:
        value["service_version"] = "dingtalk-realtime-durable-v2"
        value["process_id"] = os.getpid()
        value["import_control"] = control.snapshot().public()
        value["import_inflight"] = bool((runtime or {}).get("inflight", False))
        value["import_inflight_target"] = (runtime or {}).get("inflight_target")
        value["import_inflight_started_at"] = (runtime or {}).get("inflight_started_at")
    temporary = state / "health.json.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, state / "health.json")


async def health(state, db, client, stop, runtime=None, control=None):
    connected = None
    while not stop.is_set():
        write_health(state, db, client, runtime, control)
        if (client.websocket is not None) != connected:
            connected = client.websocket is not None
            status("stream_connected" if connected else "stream_disconnected")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass


async def main(options):
    import fcntl
    os.umask(0o077)
    auth = credentials(options.credentials)
    state = Path(options.state_dir)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = state.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("state directory must be owner-only")
    lock = (state / "service.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = sqlite3.connect(state / "inbox.sqlite3")
    initialize_database(db)
    client = sdk.DingTalkStreamClient(sdk.Credential(auth["client_id"], auth["client_secret"]),
        websocket_connect_options={"open_timeout": 10, "ping_interval": 20, "ping_timeout": 20, "close_timeout": 5})
    if not callable(getattr(client, "stop", None)):
        raise RuntimeError("installed SDK lacks required async stop API")
    client.register_all_event_handler(InboxHandler(db, auth["corp_id"]))
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    runtime = {"inflight": False}
    control = ImportControl(getattr(options, "import_control", None), options.bench, options.site,
        getattr(options, "allowed_bench", ()))
    stream, jobs = asyncio.create_task(client.start()), asyncio.create_task(worker(options, db, stop, runtime))
    monitor, stopping = asyncio.create_task(health(state, db, client, stop, runtime, control)), asyncio.create_task(stop.wait())
    status("service_started")
    try:
        await asyncio.wait((stream, jobs, monitor, stopping), return_when=asyncio.FIRST_COMPLETED)
        if not stopping.done():
            raise RuntimeError("service task exited")
    finally:
        stop.set()
        await client.stop()
        await asyncio.gather(stream, jobs, monitor, return_exceptions=True)
        stopping.cancel()
        write_health(state, db, client, runtime, control)
        db.close()
        lock.close()
        status("service_stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--state-dir", default="/var/lib/dingtalk-attendance-stream")
    parser.add_argument("--bench", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--allowed-bench", action="append", default=[],
        help="Additional trusted import target; repeat for each release bench")
    parser.add_argument("--import-control", help="Optional owner-only import control JSON; configured but unsafe/missing means paused")
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception as error:
        status("service_failed", error_type=type(error).__name__)
        sys.exit(1)
