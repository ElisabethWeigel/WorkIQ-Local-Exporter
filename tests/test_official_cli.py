import json
from subprocess import CompletedProcess

import pytest

from workiq_exporter.official_cli import OfficialCliClient, OfficialCliError


def test_official_cli_uses_account_and_parses_structured_answer(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "workiq_exporter.official_cli.shutil.which", lambda executable: "workiq.CMD"
    )

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "response": "Corporate answer",
                    "conversationId": "conversation-1",
                    "citations": [
                        {"title": "Email", "url": "https://example.test/email"}
                    ],
                }
            ),
            "",
        )

    monkeypatch.setattr("workiq_exporter.official_cli.subprocess.run", run)

    answer = OfficialCliClient("user@example.com").ask(
        "Question", time_zone="Europe/Berlin"
    )

    assert calls[0][:5] == [
        "workiq.CMD",
        "ask",
        "--json",
        "--account",
        "user@example.com",
    ]
    assert answer.text == "Corporate answer"
    assert answer.context_id == "conversation-1"
    assert answer.citations[0].title == "Email"


def test_official_cli_surfaces_eula_error(monkeypatch) -> None:
    payload = {"isError": True, "error": "Run 'workiq accept-eula'."}
    monkeypatch.setattr(
        "workiq_exporter.official_cli.shutil.which", lambda executable: "workiq.CMD"
    )
    monkeypatch.setattr(
        "workiq_exporter.official_cli.subprocess.run",
        lambda command, **kwargs: CompletedProcess(
            command, 1, json.dumps(payload), ""
        ),
    )

    with pytest.raises(OfficialCliError, match="accept-eula"):
        OfficialCliClient("user@example.com").ask("Question", time_zone="UTC")


def test_official_cli_reports_missing_executable(monkeypatch) -> None:
    monkeypatch.setattr(
        "workiq_exporter.official_cli.shutil.which", lambda executable: None
    )

    with pytest.raises(OfficialCliError, match="not installed or is not on PATH"):
        OfficialCliClient("user@example.com").ask("Question", time_zone="UTC")