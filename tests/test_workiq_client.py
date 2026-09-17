from typing import Any

import pytest
import requests

from workiq_exporter.workiq_client import WorkIQClient, WorkIQError


class FakeResponse:
    def __init__(self, status_code: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def completed_response() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": "request-id",
        "result": {
            "task": {
                "contextId": "context-1",
                "status": {"state": "TASK_STATE_COMPLETED"},
                "artifacts": [
                    {
                        "parts": [
                            {
                                "text": "The answer",
                                "citations": [
                                    {"title": "Source", "url": "https://example.test/item"}
                                ],
                            }
                        ]
                    }
                ],
            }
        },
    }


def test_ask_sends_a2a_v1_envelope_and_parses_answer() -> None:
    session = FakeSession([FakeResponse(200, completed_response())])
    client = WorkIQClient("secret-token", session=session, max_retries=0)

    answer = client.ask("What changed?", time_zone="America/Los_Angeles")

    assert answer.text == "The answer"
    assert answer.context_id == "context-1"
    assert answer.citations[0].title == "Source"
    call = session.calls[0]
    assert call["url"] == "https://workiq.svc.cloud.microsoft/a2a/"
    assert call["headers"]["A2A-Version"] == "1.0"
    assert call["headers"]["Authorization"] == "Bearer secret-token"
    assert call["json"]["method"] == "SendMessage"
    assert call["json"]["params"]["message"]["metadata"]["Location"]["timeZone"] == "America/Los_Angeles"


def test_json_rpc_error_is_reported() -> None:
    session = FakeSession(
        [FakeResponse(200, {"jsonrpc": "2.0", "error": {"message": "Method failed"}})]
    )

    with pytest.raises(WorkIQError, match="Method failed"):
        WorkIQClient("token", session=session, max_retries=0).ask("Question", time_zone="UTC")


def test_forbidden_response_has_actionable_error() -> None:
    session = FakeSession([FakeResponse(403, {})])

    with pytest.raises(WorkIQError, match="not enabled or consented"):
        WorkIQClient("token", session=session, max_retries=0).ask("Question", time_zone="UTC")
