import json
from pathlib import Path

from workiq_exporter import cli
from workiq_exporter.auth import AuthSession
from workiq_exporter.models import Citation
from workiq_exporter.workiq_client import WorkIQAnswer


class FakeClient:
    def __init__(self, access_token: str) -> None:
        assert access_token == "token"

    def ask(self, question: str, *, time_zone: str, context_id: str | None = None) -> WorkIQAnswer:
        assert question == "What changed?"
        assert time_zone == "UTC"
        assert context_id is None
        return WorkIQAnswer(
            "A concise answer",
            "context-1",
            [Citation(title="Source", url="https://example.test")],
        )


def set_environment(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("WORKIQ_TENANT_ID", "tenant-1")
    monkeypatch.setenv("WORKIQ_CLIENT_ID", "client-1")
    monkeypatch.setenv("WORKIQ_PROVIDER", "direct")
    monkeypatch.setenv("WORKIQ_DATA_PATH", str(path))
    monkeypatch.setenv("WORKIQ_TIME_ZONE", "UTC")
    monkeypatch.setattr(
        cli,
        "authenticate",
        lambda tenant_id, client_id: AuthSession("token", tenant_id, "user-1"),
    )
    monkeypatch.setattr(cli, "WorkIQClient", FakeClient)
    monkeypatch.setattr(cli, "JsonRepository", insecure_repository)


def insecure_repository(path: Path):
    from workiq_exporter.json_repository import JsonRepository

    return JsonRepository(path, secure_directory=False)


def test_ask_saves_only_after_confirmation(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "qa.json"
    set_environment(monkeypatch, path)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    assert cli.main(["ask", "What changed?"]) == 0

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["items"][0]["question"] == "What changed?"
    assert stored["items"][0]["answer"] == "A concise answer"


def test_ask_does_not_write_when_confirmation_is_declined(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "qa.json"
    set_environment(monkeypatch, path)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    assert cli.main(["ask", "What changed?"]) == 0
    assert not path.exists()


def test_list_shows_question_and_answer_previews(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / "qa.json"
    set_environment(monkeypatch, path)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert cli.main(["ask", "What changed?"]) == 0
    capsys.readouterr()

    assert cli.main(["list"]) == 0

    output = capsys.readouterr().out
    assert "Question: What changed?" in output
    assert "Answer: A concise answer" in output


def test_purge_all_does_not_require_identity_configuration(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "qa.json"
    monkeypatch.delenv("WORKIQ_TENANT_ID", raising=False)
    monkeypatch.delenv("WORKIQ_CLIENT_ID", raising=False)
    monkeypatch.setenv("WORKIQ_PROVIDER", "direct")
    monkeypatch.setenv("WORKIQ_DATA_PATH", str(path))
    monkeypatch.setattr(cli, "JsonRepository", insecure_repository)

    assert cli.main(["purge", "--all"]) == 0

