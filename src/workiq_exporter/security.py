from __future__ import annotations

import csv
import subprocess
from pathlib import Path


class LocalSecurityError(RuntimeError):
    pass


def restrict_directory_to_current_user(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW
    try:
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
            creationflags=flags,
        )
        row = next(csv.reader([identity.stdout.strip()]))
        user_sid = row[-1]
        if not user_sid.startswith("S-"):
            raise ValueError("whoami did not return a Windows SID")
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{user_sid}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
                "*S-1-5-32-544:(OI)(CI)F",
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=flags,
        )
    except (OSError, subprocess.CalledProcessError, StopIteration, ValueError) as error:
        raise LocalSecurityError(f"cannot secure local data directory {path}: {error}") from error
