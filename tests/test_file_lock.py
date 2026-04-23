from pathlib import Path

import pytest

from scripts.file_lock import FileLock, lock_file


def test_file_lock_acquire_and_release(tmp_path: Path):
    lock_path = tmp_path / ".test.lock"
    lock = FileLock(lock_path, timeout=0.01)
    assert lock.acquire() is True
    assert lock_path.exists()
    lock.release()


def test_file_lock_times_out_when_already_held(tmp_path: Path):
    lock_path = tmp_path / ".test.lock"
    first = FileLock(lock_path, timeout=0.01)
    second = FileLock(lock_path, timeout=0.01)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
        second.release()


def test_lock_file_context_manager_releases_lock(tmp_path: Path):
    target = tmp_path / "ROADMAP.md"
    target.write_text("x", encoding="utf-8")
    with lock_file(target, timeout=0.01):
        assert (tmp_path / ".heartbeat.lock").exists()
    lock = FileLock(tmp_path / ".heartbeat.lock", timeout=0.01)
    assert lock.acquire() is True
    lock.release()


def test_file_lock_context_manager_raises_on_timeout(tmp_path: Path):
    lock_path = tmp_path / ".test.lock"
    first = FileLock(lock_path, timeout=0.01)
    assert first.acquire() is True
    try:
        with pytest.raises(TimeoutError):
            with FileLock(lock_path, timeout=0.01):
                pass
    finally:
        first.release()


def test_file_lock_recovers_from_stale_lock(tmp_path: Path):
    """Stale lock (from crashed process) is detected and removed via mtime."""
    lock_path = tmp_path / ".test.lock"
    # Simulate a stale lock: create file and backdate its mtime
    lock_path.write_text("stale", encoding="utf-8")
    import os, time
    stale_time = time.time() - 2  # 2 seconds ago
    os.utime(lock_path, (stale_time, stale_time))
    # Second process should acquire despite stale lock if timeout > 1s
    second = FileLock(lock_path, timeout=2.0)
    assert second.acquire() is True
    second.release()
    # Cleanup
    try:
        first.release()
    except Exception:
        pass
