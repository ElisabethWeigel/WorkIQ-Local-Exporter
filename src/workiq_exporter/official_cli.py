from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .models import Citation
from .workiq_client import WorkIQAnswer


class OfficialCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficialCliClient:
    account: str
    executable: str = "workiq"
    timeout: float = 120.0

    def ask(
        self,
        question: str,
        *,
        time_zone: str,
        context_id: str | None = None,
    ) -> WorkIQAnswer:
        del time_zone  # The official CLI derives location from the signed-in user.
        executable = shutil.which(self.executable)
        if executable is None:
            raise OfficialCliError(
                "The official Work IQ CLI is not installed or is not on PATH. Run: "
                "npm install -g @microsoft/workiq"
            )
        command = [
            executable,
            "ask",
            "--json",
            "--account",
            self.account,
            "--question",
            question,
        ]
        if context_id:
            command.extend(["--conversation-id", context_id])
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )
        except FileNotFoundError as error:
            raise OfficialCliError(f"Work IQ CLI executable disappeared: {executable}") from error
        except subprocess.TimeoutExpired as error:
            raise OfficialCliError("The official Work IQ CLI timed out") from error

        output = completed.stdout.strip() or completed.stderr.strip()
        try:
            value = json.loads(output)
        except json.JSONDecodeError as error:
            detail = output or f"exit code {completed.returncode}"
            raise OfficialCliError(f"Work IQ CLI returned invalid JSON: {detail}") from error
        if not isinstance(value, dict):
            raise OfficialCliError("Work IQ CLI response must be a JSON object")
        if completed.returncode != 0 or value.get("isError") is True:
            detail = value.get("error") or value.get("message") or output
            raise OfficialCliError(str(detail).strip())
        return _parse_answer(value)


def _parse_answer(value: dict[str, Any]) -> WorkIQAnswer:
    text = _first_string(value, ("answer", "response", "text", "content"))
    if not text:
        raise OfficialCliError("Work IQ CLI completed without answer text")
    context_id = _first_string(
        value,
        ("conversationId", "conversation_id", "contextId", "context_id"),
    )
    citations = _collect_citations(value)
    return WorkIQAnswer(text=text, context_id=context_id, citations=citations)


def _first_string(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            found = _first_string(candidate, keys)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _first_string(candidate, keys)
            if found:
                return found
    return None


def _collect_citations(value: Any) -> list[Citation]:
    citations: list[Citation] = []
    if isinstance(value, dict):
        raw_citations = value.get("citations")
        if isinstance(raw_citations, list):
            for raw in raw_citations:
                if isinstance(raw, dict):
                    citations.append(Citation.from_dict(raw))
        for key, candidate in value.items():
            if key != "citations":
                citations.extend(_collect_citations(candidate))
    elif isinstance(value, list):
        for candidate in value:
            citations.extend(_collect_citations(candidate))
    return citations