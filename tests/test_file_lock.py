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
