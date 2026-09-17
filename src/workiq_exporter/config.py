from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .json_repository import default_data_path

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the supported runtime.
    winreg = None  # type: ignore[assignment]


def _read_windows_user_environment() -> dict[str, str]:
    if winreg is None:
        return {}
    values: dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                if isinstance(value, str):
                    values[name] = value
                index += 1
    except OSError:
        return {}
    return values


def _setting(name: str, user_environment: Mapping[str, str], default: str = "") -> str:
    return os.environ.get(name, user_environment.get(name, default))


@dataclass(frozen=True)
class Config:
    tenant_id: str
    client_id: str
    account: str
    provider: str
    data_path: Path
    retention_hours: int
    time_zone: str

    @classmethod
    def from_environment(cls, *, require_identity: bool = True) -> Config:
        user_environment = _read_windows_user_environment()
        tenant_id = _setting("WORKIQ_TENANT_ID", user_environment).strip()
        client_id = _setting("WORKIQ_CLIENT_ID", user_environment).strip()
        account = _setting("WORKIQ_ACCOUNT", user_environment).strip()
        provider = _setting("WORKIQ_PROVIDER", user_environment, "direct").strip()
        if provider not in {"direct", "official-cli"}:
            raise ValueError("WORKIQ_PROVIDER must be direct or official-cli")
        if require_identity and not tenant_id:
            raise ValueError("WORKIQ_TENANT_ID must be set")
        if require_identity and provider == "direct" and not client_id:
            raise ValueError("WORKIQ_CLIENT_ID must be set for the direct provider")
        if require_identity and provider == "official-cli" and not account:
            raise ValueError("WORKIQ_ACCOUNT must be set for the official-cli provider")
        retention_hours = int(
            _setting("WORKIQ_RETENTION_HOURS", user_environment, "24")
        )
        if retention_hours < 1:
            raise ValueError("WORKIQ_RETENTION_HOURS must be at least 1")
        data_path_value = _setting("WORKIQ_DATA_PATH", user_environment)
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            account=account,
            provider=provider,
            data_path=Path(data_path_value) if data_path_value else default_data_path(),
            retention_hours=retention_hours,
            time_zone=(
                _setting("WORKIQ_TIME_ZONE", user_environment, "UTC").strip()
                or "UTC"
            ),
        )
