"""Agent state definitions."""

from __future__ import annotations

from typing import TypedDict


class AnsaAgentState(TypedDict, total=False):
    """State carried through the ANSA workflow graph."""
    experiment_id: str   # UUID assigned at workflow start
    model_path: str
    script_path: str
    status: str          # "pending" | "running" | "success" | "error"
    result: dict | None
    error: str | None
    stdout_lines: list[str]
    stderr_lines: list[str]
    process_id: str | None  # key into ProcessRegistry for shared ANSA processes
