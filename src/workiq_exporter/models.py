from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class Citation:
    title: str | None = None
    url: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Citation:
        return cls(title=value.get("title"), url=value.get("url"))


@dataclass(frozen=True)
class QuestionAnswer:
    id: str
    tenant_id: str
    user_oid: str
    question: str
    answer: str
    generated_at: str
    expires_at: str
    citations: list[Citation] = field(default_factory=list)
    conversation_id: str | None = None
    context_id: str | None = None
    protocol_version: str = "1.0"

    def __post_init__(self) -> None:
        required = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_oid": self.user_oid,
            "question": self.question,
            "answer": self.answer,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"required fields are empty: {', '.join(missing)}")
        if parse_timestamp(self.expires_at) <= parse_timestamp(self.generated_at):
            raise ValueError("expires_at must be later than generated_at")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> QuestionAnswer:
        data = dict(value)
        citations = data.get("citations", [])
        if not isinstance(citations, list):
            raise ValueError("citations must be a list")
        data["citations"] = [Citation.from_dict(item) for item in citations]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QuestionAnswerFile:
    schema_version: int
    updated_at: str
    items: list[QuestionAnswer]

    @classmethod
    def empty(cls, now: datetime) -> QuestionAnswerFile:
        return cls(schema_version=1, updated_at=now.astimezone(UTC).isoformat(), items=[])

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> QuestionAnswerFile:
        if value.get("schema_version") != 1:
            raise ValueError("unsupported schema_version")
        updated_at = value.get("updated_at")
        items = value.get("items")
        if not isinstance(updated_at, str) or not isinstance(items, list):
            raise ValueError("invalid question and answer file")
        parse_timestamp(updated_at)
        return cls(1, updated_at, [QuestionAnswer.from_dict(item) for item in items])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "items": [item.to_dict() for item in self.items],
        }
