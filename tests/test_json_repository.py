import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from workiq_exporter.json_repository import JsonRepository, RepositoryError
from workiq_exporter.models import QuestionAnswer


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def make_item(item_id: str, *, expires_in: timedelta = timedelta(hours=24)) -> QuestionAnswer:
    return QuestionAnswer(
        id=item_id,
        tenant_id="tenant-1",
        user_oid="user-1",
        question=f"Question {item_id}",
        answer=f"Answer {item_id}",
        generated_at=NOW.isoformat(),
        expires_at=(NOW + expires_in).isoformat(),
    )


def test_add_uses_versioned_json_and_lists_owner_items(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    repository = JsonRepository(path, clock=lambda: NOW, secure_directory=False)

    repository.add(make_item("one"))

    assert [item.id for item in repository.list_for("tenant-1", "user-1")] == ["one"]
    assert repository.list_for("tenant-1", "other-user") == []
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1
    assert stored["items"][0]["question"] == "Question one"


def test_expired_items_are_removed_before_listing(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    repository = JsonRepository(path, clock=lambda: NOW, secure_directory=False)
    repository.add(make_item("expired", expires_in=timedelta(seconds=1)))
    later = JsonRepository(
        path,
        clock=lambda: NOW + timedelta(seconds=2),
        secure_directory=False,
    )

    assert later.list_for("tenant-1", "user-1") == []
    assert json.loads(path.read_text(encoding="utf-8"))["items"] == []


def test_malformed_file_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    path.write_text("not json", encoding="utf-8")
    repository = JsonRepository(path, clock=lambda: NOW, secure_directory=False)

    with pytest.raises(RepositoryError, match="cannot read"):
        repository.add(make_item("one"))

    assert path.read_text(encoding="utf-8") == "not json"


def test_concurrent_adds_do_not_lose_updates(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"

    def add(index: int) -> None:
        JsonRepository(path, clock=lambda: NOW, secure_directory=False).add(make_item(str(index)))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(add, range(12)))

    items = JsonRepository(path, clock=lambda: NOW, secure_directory=False).list_for(
        "tenant-1", "user-1"
    )
    assert {item.id for item in items} == {str(index) for index in range(12)}


def test_delete_is_scoped_to_authenticated_owner(tmp_path: Path) -> None:
    repository = JsonRepository(
        tmp_path / "qa.json", clock=lambda: NOW, secure_directory=False
    )
    repository.add(make_item("one"))

    assert repository.delete("one", "tenant-1", "other-user") is False
    assert repository.delete("one", "tenant-1", "user-1") is True