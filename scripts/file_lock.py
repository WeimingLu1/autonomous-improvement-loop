#!/usr/bin/env python3
"""File locking helpers using fcntl.flock for exclusive advisory locks.

Prevents concurrent cron runs from corrupting state files by ensuring
exclusive access during read/write operations.
"""

from __future__ import annotations

import fcntl
import sys
import time
from contextlib import contextmanager
from pathlib import Path


class FileLock:
    """Exclusive advisory file lock using fcntl.flock.

    Uses non-blocking acquire with timeout fallback. On acquisition failure,
    logs an error and raises LockNotAcquired rather than hanging indefinitely.
    """

    def __init__(self, lock_path: Path, timeout: float = 30.0) -> None:
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd = None

    def acquire(self) -> bool:
        """Acquire the exclusive lock with timeout.

        Returns True if lock was acquired, False on timeout.
        Does not block - uses LOCK_NB flag.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self.lock_path, "w")
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                if time.monotonic() - start >= self.timeout:
                    return False
                time.sleep(0.1)

    def release(self) -> None:
        """Release the exclusive lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                self._fd.close()
            except (IOError, OSError):
                pass
            self._fd = None

    def __enter__(self) -> "FileLock":
        if not self.acquire():
            self.release()
            print(
                f"ERROR: could not acquire lock {self.lock_path} within {self.timeout}s",
                file=sys.stderr,
            )
            raise TimeoutError(
                f"Could not acquire lock {self.lock_path} within {self.timeout}s"
            )
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


@contextmanager
def lock_file(path: Path, timeout: float = 30.0):
    """Context manager for exclusive file locking on a state file.

    The lock file path is derived from the target path:
        path.parent / ".heartbeat.lock"

    Args:
        path: Path to the file being locked (lock is derived from this)
        timeout: Seconds to wait before giving up (default: 30)

    Yields:
        FileLock instance

    Raises:
        TimeoutError: If lock cannot be acquired within timeout.
    """
    lock_path = path.parent / ".heartbeat.lock"
    lock = FileLock(lock_path, timeout=timeout)
    try:
        lock.acquire()
        yield lock
    finally:
        lock.release()


def heartbeat_lock(heartbeat_path: Path, timeout: float = 30.0):
    """Backward-compatible helper for locking a state file path.

    Args:
        heartbeat_path: Path to the file being locked
        timeout: Seconds to wait before giving up (default: 30)

    Yields:
        FileLock instance

    Raises:
        TimeoutError: If lock cannot be acquired within timeout.
    """
    return lock_file(heartbeat_path, timeout=timeout)
