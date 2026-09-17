from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from .models import Citation


WORK_IQ_ENDPOINT = "https://workiq.svc.cloud.microsoft/a2a/"


class WorkIQError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkIQAnswer:
    text: str
    context_id: str | None
    citations: list[Citation] = field(default_factory=list)


class WorkIQClient:
    def __init__(
        self,
        access_token: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._access_token = access_token
        self._session = session or requests.Session()
        self._timeout = timeout
        self._max_retries = max_retries

    def ask(
        self,
        question: str,
        *,
        time_zone: str,
        context_id: str | None = None,
    ) -> WorkIQAnswer:
        if not question.strip():
            raise ValueError("question cannot be empty")
        local_now = datetime.now().astimezone()
        offset = local_now.utcoffset()
        message: dict[str, Any] = {
            "role": "ROLE_USER",
            "messageId": str(uuid.uuid4()),
            "parts": [{"text": question.strip()}],
            "metadata": {
                "Location": {
                    "timeZoneOffset": int(offset.total_seconds() / 60) if offset else 0,
                    "timeZone": time_zone,
                }
            },
        }
        if context_id:
            message["contextId"] = context_id
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "SendMessage",
            "params": {"message": message},
        }
        response = self._post(body)
        return self._parse_answer(response)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "A2A-Version": "1.0",
        }
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    WORK_IQ_ENDPOINT,
                    headers=headers,
                    json=body,
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                raise WorkIQError(f"Work IQ request failed: {error}") from error
            if response.status_code != 429 or attempt == self._max_retries:
                break
            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = min(max(float(retry_after), 0), 10)
            except ValueError:
                delay = 1
            time.sleep(delay)
        if response.status_code == 401:
            raise WorkIQError("Work IQ rejected the access token (401)")
        if response.status_code == 403:
            raise WorkIQError("Work IQ access is not enabled or consented (403)")
        if response.status_code == 429:
            raise WorkIQError("Work IQ request was throttled (429)")
        try:
            response.raise_for_status()
            value = response.json()
        except (requests.RequestException, ValueError) as error:
            raise WorkIQError("Work IQ returned an invalid response") from error
        if not isinstance(value, dict):
            raise WorkIQError("Work IQ response must be a JSON object")
        return value

    @staticmethod
    def _parse_answer(value: dict[str, Any]) -> WorkIQAnswer:
        if "error" in value:
            error = value["error"]
            message = error.get("message", "unknown JSON-RPC error") if isinstance(error, dict) else str(error)
            raise WorkIQError(f"Work IQ JSON-RPC error: {message}")
        try:
            task = value["result"]["task"]
            state = task["status"]["state"]
            artifacts = task["artifacts"]
        except (KeyError, TypeError) as error:
            raise WorkIQError("Work IQ response is missing task data") from error
        if state != "TASK_STATE_COMPLETED":
            raise WorkIQError(f"Work IQ task did not complete: {state}")
        texts: list[str] = []
        citations: list[Citation] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            for part in artifact.get("parts", []):
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
                citation_values = part.get("citations", [])
                if isinstance(citation_values, list):
                    for citation in citation_values:
                        if isinstance(citation, dict):
                            citations.append(Citation.from_dict(citation))
        if not texts:
            raise WorkIQError("Work IQ completed without answer text")
        return WorkIQAnswer("\n".join(texts), task.get("contextId"), citations)
