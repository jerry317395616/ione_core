#!/usr/bin/env python3
"""Owner-only import gate. No credentials, database, SDK, or network access."""
import argparse
from contextlib import asynccontextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

MAX_BYTES = 4096


class UnsafeControl(ValueError):
    pass


@dataclass(frozen=True)
class TargetPolicy:
    """Trusted launch configuration, independent of the mutable control file."""

    site: str
    allowed_benches: frozenset[str]

    def __post_init__(self):
        if not isinstance(self.site, str) or not self.site.strip() or not self.allowed_benches:
            raise UnsafeControl("missing_target_policy")
        for bench in self.allowed_benches:
            if not isinstance(bench, str) or not Path(bench).is_absolute() or ".." in Path(bench).parts:
                raise UnsafeControl("invalid_target_policy")

    def validate(self, bench, site):
        if not isinstance(bench, str) or bench not in self.allowed_benches or site != self.site:
            raise UnsafeControl("invalid_target")


@dataclass(frozen=True)
class Decision:
    configured: bool
    valid: bool
    paused: bool
    bench: str
    site: str
    generation: str = ""
    error: str = ""

    def public(self):
        return {
            "configured": self.configured,
            "valid": self.valid,
            "paused": self.paused,
            "target": "configured" if self.bench else "unconfigured",
            "generation": self.generation,
            "error": self.error,
        }


def _check_file(fd):
    value = os.fstat(fd)
    if not stat.S_ISREG(value.st_mode) or stat.S_IMODE(value.st_mode) != 0o600 or value.st_uid != os.getuid() or value.st_nlink != 1:
        raise UnsafeControl("unsafe_file")


def _open_directory(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or path.parent.resolve(strict=True) != path.parent:
        raise UnsafeControl("unsafe_path")
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    value = os.fstat(fd)
    if not stat.S_ISDIR(value.st_mode) or stat.S_IMODE(value.st_mode) != 0o700 or value.st_uid != os.getuid():
        os.close(fd)
        raise UnsafeControl("unsafe_directory")
    return fd


def _open_lock(dirfd, name):
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
    try:
        _check_file(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(path, dirfd, policy):
    fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        _check_file(fd)
        with os.fdopen(fd, "rb", closefd=False) as handle:
            payload = handle.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise UnsafeControl("oversized_control")
        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {"version", "pause_import", "bench", "site", "generation"}:
            raise UnsafeControl("invalid_schema")
        if type(value["version"]) is not int or value["version"] != 1 or type(value["pause_import"]) is not bool:
            raise UnsafeControl("invalid_schema")
        policy.validate(value["bench"], value["site"])
        if not isinstance(value["generation"], str) or len(value["generation"]) != 32 or any(c not in "0123456789abcdef" for c in value["generation"]):
            raise UnsafeControl("invalid_generation")
        return Decision(True, True, value["pause_import"], value["bench"], policy.site, value["generation"])
    finally:
        os.close(fd)


def _closed(error, site):
    return Decision(True, False, True, "", site, error=error)


class ImportControl:
    def __init__(self, path=None, bench=None, site=None, allowed_benches=()):
        self.path = str(path) if path else None
        self.policy = TargetPolicy(site, frozenset((bench, *(allowed_benches or ()))))
        self.default = Decision(False, True, False, str(bench), site)

    def snapshot(self):
        if not self.path:
            return self.default
        directory = lock = None
        try:
            directory = _open_directory(self.path)
            decision = _read(self.path, directory, self.policy)
            lock = _open_lock(directory, Path(self.path).name + ".dispatch.lock")
            return decision
        except (OSError, ValueError, TypeError, KeyError):
            return _closed("control_unavailable_or_unsafe", self.policy.site)
        finally:
            if lock is not None:
                os.close(lock)
            if directory is not None:
                os.close(directory)

    @asynccontextmanager
    async def dispatch(self):
        """Hold the shared boundary lock until import has stopped AND its result is stored."""
        if not self.path:
            yield self.default
            return
        directory = lock = None
        try:
            try:
                directory = _open_directory(self.path)
                lock = _open_lock(directory, Path(self.path).name + ".dispatch.lock")
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                decision = _read(self.path, directory, self.policy)
            except (OSError, ValueError, TypeError, KeyError):
                decision = _closed("control_unavailable_or_unsafe", self.policy.site)
            yield decision
        finally:
            if lock is not None:
                os.close(lock)
            if directory is not None:
                os.close(directory)


def _publish(path, directory, paused, bench, site):
    value = {"version": 1, "pause_import": paused, "bench": bench, "site": site, "generation": uuid.uuid4().hex}
    data = (json.dumps(value, sort_keys=True) + "\n").encode()
    name = "." + Path(path).name + "." + uuid.uuid4().hex + ".tmp"
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(fd)
        os.rename(name, Path(path).name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(fd)
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass
    return value, hashlib.sha256(data).hexdigest()


def set_control(path, paused, bench, timeout=300, *, site, allowed_benches):
    """Pause first; drain existing dispatch; publish requested state while exclusive.

    The returned drained boundary includes subprocess exit and inbox result commit.
    A timeout leaves pause_import=true and never authorizes a maintenance write freeze.
    Callers must use this function/CLI, not an ad-hoc JSON editor, for drain proof.
    """
    policy = TargetPolicy(site, frozenset(allowed_benches))
    policy.validate(bench, site)
    if type(paused) is not bool or not 0 < timeout <= 3600:
        raise UnsafeControl("invalid_control_request")
    directory = _open_directory(path)
    writer = dispatch = None
    try:
        writer = _open_lock(directory, Path(path).name + ".writer.lock")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("control_writer_timeout")
                time.sleep(0.05)
        # Atomic replacement also repairs a corrupt/missing control fail-closed.
        _publish(path, directory, True, bench, site)
        dispatch = _open_lock(directory, Path(path).name + ".dispatch.lock")
        while True:
            try:
                fcntl.flock(dispatch, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("import_drain_timeout")
                time.sleep(0.05)
        value, digest = _publish(path, directory, paused, bench, site)
        return {"ok": True, "drained": True, "paused": paused, "target": "configured", "generation": value["generation"], "sha256": digest}
    finally:
        if dispatch is not None:
            os.close(dispatch)
        if writer is not None:
            os.close(writer)
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True)
    parser.add_argument("--bench", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--allowed-bench", action="append", required=True,
        help="Trusted target allowlist; repeat each service launch target exactly")
    parser.add_argument("--pause", required=True, choices=("yes", "no"))
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    try:
        print(json.dumps(set_control(args.control, args.pause == "yes", args.bench, args.timeout,
            site=args.site, allowed_benches=args.allowed_bench), sort_keys=True))
    except Exception as error:
        print(json.dumps({"ok": False, "drained": False, "error_type": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
