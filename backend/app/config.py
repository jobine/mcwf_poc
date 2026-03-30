"""Centralized configuration — reads from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    experiments_dir: Path
    scripts_dir: Path
    data_shared_dir: Path
    graph_config_path: Path

    model_config = {
        "env_file": str(_BACKEND_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
