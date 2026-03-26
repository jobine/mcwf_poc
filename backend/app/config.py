"""Centralized configuration — reads from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    experiments_dir: Path = _BACKEND_ROOT / "experiments"
    scripts_dir: Path = _BACKEND_ROOT / "scripts"
    data_shared_dir: Path = _BACKEND_ROOT / "data" / "shared"

    model_config = {
        "env_file": str(_BACKEND_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
