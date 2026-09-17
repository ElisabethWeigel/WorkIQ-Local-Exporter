from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterator

from .models import QuestionAnswer, QuestionAnswerFile, parse_timestamp
from .security import restrict_directory_to_current_user

try:
    import msvcrt
except ImportError:  # pragma: no cover - Windows is the supported runtime.
    msvcrt = None  # type: ignore[assignment]


class RepositoryError(RuntimeError):
    pass


def default_data_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RepositoryError("LOCALAPPDATA is not set")
    return Path(local_app_data) / "WorkIQExporter" / "qa.json"


class JsonRepository:
    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        lock_timeout: float = 5.0,
        secure_directory: bool = True,
    ) -> None:
        self.path = path or default_data_path()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock_timeout = lock_timeout
        self._secure_directory = secure_directory
        self._directory_secured = False

    def list_for(self, tenant_id: str, user_oid: str) -> list[QuestionAnswer]:
        with self._locked():
            document = self._load()
            changed = self._remove_expired(document)
            if changed:
                self._write(document)
            return [
                item
                for item in document.items
                if item.tenant_id == tenant_id and item.user_oid == user_oid
            ]

    def get(self, item_id: str, tenant_id: str, user_oid: str) -> QuestionAnswer | None:
        return next(
            (
                item
                for item in self.list_for(tenant_id, user_oid)
                if item.id == item_id
            ),
            None,
        )

    def add(self, item: QuestionAnswer) -> None:
        with self._locked():
            document = self._load()
            self._remove_expired(document)
            if any(existing.id == item.id for existing in document.items):
                raise RepositoryError(f"duplicate item id: {item.id}")
            document.items.append(item)
            self._write(document)

    def delete(self, item_id: str, tenant_id: str, user_oid: str) -> bool:
        with self._locked():
            document = self._load()
            self._remove_expired(document)
            original_count = len(document.items)
            document.items = [
                item
                for item in document.items
                if not (
                    item.id == item_id
                    and item.tenant_id == tenant_id
                    and item.user_oid == user_oid
                )
            ]
            changed = len(document.items) != original_count
            self._write(document)
            return changed

    def purge(self, tenant_id: str | None = None, user_oid: str | None = None) -> int:
        if (tenant_id is None) != (user_oid is None):
            raise ValueError("tenant_id and user_oid must be provided together")
        with self._locked():
            document = self._load()
            original_count = len(document.items)
            if tenant_id is None:
                document.items = []
            else:
                document.items = [
                    item
                    for item in document.items
                    if item.tenant_id != tenant_id or item.user_oid != user_oid
                ]
            self._write(document)
            return original_count - len(document.items)

    def _load(self) -> QuestionAnswerFile:
        if not self.path.exists():
            return QuestionAnswerFile.empty(self._clock())
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("top-level JSON value must be an object")
            return QuestionAnswerFile.from_dict(value)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise RepositoryError(f"cannot read {self.path}: {error}") from error

    def _remove_expired(self, document: QuestionAnswerFile) -> bool:
        now = self._clock().astimezone(UTC)
        active = [item for item in document.items if parse_timestamp(item.expires_at) > now]
        changed = len(active) != len(document.items)
        document.items = active
        return changed

    def _write(self, document: QuestionAnswerFile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document.updated_at = self._clock().astimezone(UTC).isoformat()
        payload = json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise RepositoryError(f"cannot write {self.path}: {error}") from error

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if msvcrt is None:
            raise RepositoryError("file locking requires Windows")
        if self._secure_directory and not self._directory_secured:
            restrict_directory_to_current_user(self.path.parent)
            self._directory_secured = True
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+b") as lock_file:
            deadline = time.monotonic() + self._lock_timeout
            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise RepositoryError(f"timed out waiting for {lock_path}") from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
