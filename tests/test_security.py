from pathlib import Path
from subprocess import CompletedProcess

from workiq_exporter.security import restrict_directory_to_current_user


def test_directory_acl_uses_stable_windows_sids(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "whoami":
            return CompletedProcess(command, 0, '"DOMAIN\\user","S-1-5-21-123"\n', "")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("workiq_exporter.security.subprocess.run", run)

    restrict_directory_to_current_user(tmp_path / "data")

    assert calls[1][0] == "icacls"
    assert "/inheritance:r" in calls[1]
    assert "*S-1-5-21-123:(OI)(CI)F" in calls[1]
    assert "*S-1-5-18:(OI)(CI)F" in calls[1]
    assert "*S-1-5-32-544:(OI)(CI)F" in calls[1]