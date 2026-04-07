"""Process registry — holds live AnsaProcess instances for sharing across agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.ansa_backend import AnsaProcess


class ProcessRegistry:
    """Workflow-level registry of live AnsaProcess instances, keyed by process_id."""

    def __init__(self) -> None:
        self._processes: dict[str, AnsaProcess] = {}
        self._counter: int = 0

    def get(self, process_id: str) -> AnsaProcess | None:
        """Return the process for *process_id*, or None if not registered."""
        return self._processes.get(process_id)

    def register(self, process_id: str, process: AnsaProcess) -> None:
        """Register a process under the given *process_id*."""
        self._processes[process_id] = process

    def next_id(self) -> str:
        """Generate the next auto-incrementing process ID."""
        pid = f"p{self._counter}"
        self._counter += 1
        return pid

    def shutdown_all(self) -> None:
        """Shutdown every registered process and clear the registry."""
        for proc in self._processes.values():
            try:
                proc.shutdown()
            except Exception:
                pass
        self._processes.clear()
