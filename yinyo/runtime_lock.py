"""Process lock for local JSONL runtime stores."""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType


class RuntimeLockError(RuntimeError):
    """Raised when another process already owns the local runtime store lock."""


@dataclass
class RuntimeStoreLock:
    """Exclusive process lock for local JSONL event/job/log stores."""

    path: str
    owner: str = ""
    _fd: int | None = None
    recovered_stale_owner: str = ""

    def acquire(self) -> "RuntimeStoreLock":
        resolved = Path(self.path).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.owner = self.owner or _owner()
        self._fd = self._open_exclusive(resolved)
        os.write(self._fd, (self.owner + "\n").encode("utf-8"))
        os.fsync(self._fd)
        self.path = str(resolved)
        return self

    def _open_exclusive(self, resolved: Path) -> int:
        try:
            return os.open(str(resolved), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            existing = _read_owner(resolved)
            if _is_stale_owner(existing):
                self.recovered_stale_owner = existing
                try:
                    os.remove(resolved)
                except FileNotFoundError:
                    pass
                try:
                    return os.open(str(resolved), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    existing = _read_owner(resolved)
            detail = f" Existing owner: {existing}" if existing else ""
            raise RuntimeLockError(f"Runtime store lock is already held: {resolved}.{detail}") from exc

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def __enter__(self) -> "RuntimeStoreLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def check_runtime_store_lock_available(path: str) -> tuple[bool, str]:
    lock = RuntimeStoreLock(path)
    try:
        lock.acquire()
    except RuntimeLockError as exc:
        return False, str(exc)
    else:
        recovered = lock.recovered_stale_owner
        lock.release()
        if recovered:
            return True, f"{Path(path).resolve()} (recovered stale owner: {recovered})"
        return True, str(Path(path).resolve())


def _owner() -> str:
    return f"pid={os.getpid()} host={socket.gethostname()} ts={time.time():.3f}"


def _read_owner(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _is_stale_owner(owner: str) -> bool:
    fields = _parse_owner(owner)
    try:
        pid = int(fields.get("pid", ""))
    except ValueError:
        return False
    if pid <= 0:
        return False
    if fields.get("host") != socket.gethostname():
        return False
    return not _pid_exists(pid)


def _parse_owner(owner: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in owner.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key] = value
    return fields


def _pid_exists(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
