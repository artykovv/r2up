"""Persistent user preferences for the r2up CLI."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


def _settings_file() -> Path:
    return Path.home() / ".config" / "r2up" / "settings.json"


def load_download_dir(settings_file: Optional[Path] = None) -> Optional[Path]:
    """Load the saved default download directory, if the user has set one."""
    settings_file = Path(settings_file) if settings_file else _settings_file()
    if not settings_file.is_file():
        return None

    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Could not read r2up settings file '{settings_file}': {e}") from e

    directory = settings.get("download_dir") if isinstance(settings, dict) else None
    if not isinstance(directory, str) or not directory.strip():
        raise ValueError(f"The r2up settings file '{settings_file}' has no valid download_dir.")
    return Path(directory).expanduser()


def ensure_download_dir(directory: str | Path) -> Path:
    """Create the directory if needed and return its absolute path."""
    directory = Path(directory).expanduser()
    if directory.exists() and not directory.is_dir():
        raise NotADirectoryError(f"Download location is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def save_download_dir(directory: str | Path, settings_file: Optional[Path] = None) -> Path:
    """Create and persist the default download directory."""
    directory = ensure_download_dir(directory)

    settings_file = Path(settings_file) if settings_file else _settings_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".settings.",
            suffix=".tmp",
            dir=settings_file.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump({"download_dir": str(directory)}, temp_file, indent=2)
            temp_file.write("\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, settings_file)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    return directory
