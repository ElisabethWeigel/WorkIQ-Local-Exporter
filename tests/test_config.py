from pathlib import Path

from workiq_exporter.config import Config


def test_reads_persisted_windows_values_when_process_environment_is_stale(
    tmp_path: Path, monkeypatch
) -> None:
    for name in (
        "WORKIQ_TENANT_ID",
        "WORKIQ_CLIENT_ID",
        "WORKIQ_ACCOUNT",
        "WORKIQ_PROVIDER",
        "WORKIQ_TIME_ZONE",
        "WORKIQ_DATA_PATH",
        "WORKIQ_RETENTION_HOURS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "workiq_exporter.config._read_windows_user_environment",
        lambda: {
            "WORKIQ_TENANT_ID": "tenant-from-registry",
            "WORKIQ_CLIENT_ID": "client-from-registry",
            "WORKIQ_PROVIDER": "direct",
            "WORKIQ_TIME_ZONE": "Europe/Berlin",
            "WORKIQ_DATA_PATH": str(tmp_path / "qa.json"),
            "WORKIQ_RETENTION_HOURS": "48",
        },
    )

    config = Config.from_environment()

    assert config.tenant_id == "tenant-from-registry"
    assert config.client_id == "client-from-registry"
    assert config.provider == "direct"
    assert config.time_zone == "Europe/Berlin"
    assert config.data_path == tmp_path / "qa.json"
    assert config.retention_hours == 48


def test_process_environment_overrides_persisted_windows_values(monkeypatch) -> None:
    monkeypatch.setenv("WORKIQ_TENANT_ID", "process-tenant")
    monkeypatch.setenv("WORKIQ_CLIENT_ID", "process-client")
    monkeypatch.setenv("WORKIQ_PROVIDER", "direct")
    monkeypatch.setattr(
        "workiq_exporter.config._read_windows_user_environment",
        lambda: {
            "WORKIQ_TENANT_ID": "registry-tenant",
            "WORKIQ_CLIENT_ID": "registry-client",
        },
    )

    config = Config.from_environment()

    assert config.tenant_id == "process-tenant"
    assert config.client_id == "process-client"


def test_official_cli_provider_requires_account_but_not_client_id(monkeypatch) -> None:
    monkeypatch.setenv("WORKIQ_TENANT_ID", "tenant")
    monkeypatch.setenv("WORKIQ_PROVIDER", "official-cli")
    monkeypatch.setenv("WORKIQ_ACCOUNT", "user@example.com")
    monkeypatch.delenv("WORKIQ_CLIENT_ID", raising=False)
    monkeypatch.setattr(
        "workiq_exporter.config._read_windows_user_environment", lambda: {}
    )

    config = Config.from_environment()

    assert config.account == "user@example.com"
    assert config.client_id == ""