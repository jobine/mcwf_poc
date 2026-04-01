"""ANSA agent — manages ANSA-related workflow nodes.

Provides :class:`AnsaAgent` whose :meth:`execute` method serves as a
LangGraph node function that validates inputs, launches ANSA, and runs a script.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.graph.state import AnsaAgentState


class AnsaAgent:
    """Encapsulates all ANSA-related logic for a single graph node.

    Args:
        name: Logical name for this agent (also used as the graph node name).
        model_path: Path to the ANSA model file.
        script_path: Path to the Python script to execute.
        script_kwargs: Keyword arguments forwarded to ``project.run``.
        on_event: Optional callback invoked for workflow events (stdout,
            agent lifecycle, etc.). Each event is a dict with a ``type`` key.
    """

    def __init__(
        self,
        name: str,
        model_path: str | Path,
        script_path: str | Path,
        script_kwargs: dict | None = None,
        on_event: Callable[[dict], None] | None = None,
    ):
        self._name = name
        self._model_path = Path(model_path)
        self._script_path = Path(script_path)
        self._script_kwargs = script_kwargs or {}
        self._on_event = on_event

    @property
    def name(self) -> str:
        """Logical agent name (also used as the graph node name)."""
        return self._name

    def _emit(self, event: dict) -> None:
        if self._on_event is not None:
            self._on_event(event)

    def execute(self, state: AnsaAgentState) -> AnsaAgentState:
        """Validate inputs, then open the model and execute the script.

        Emits ``agent_started``, ``stdout``, and ``agent_completed`` events.
        """
        self._emit({"type": "agent_started", "agent": self._name})

        # ── validate inputs ────────────────────────────────────────
        errors: list[str] = []
        if not self._model_path.is_file():
            errors.append(f"Model file not found: {self._model_path}")
        if not self._script_path.is_file():
            errors.append(f"Script file not found: {self._script_path}")

        if errors:
            error_msg = "; ".join(errors)
            self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
            return {
                "status": "error",
                "error": error_msg,
            }

        # ── run ANSA ───────────────────────────────────────────────
        from app.core.ansa_backend import AnsaProcess
        from app.core.project import run as project_run

        collected_lines: list[str] = []

        def _on_stdout(line: str) -> None:
            collected_lines.append(line)
            print(f"[ANSA] {line}", flush=True)
            self._emit({"type": "stdout", "data": line})

        try:
            with AnsaProcess() as backend:
                backend.start_stdout_reader(callback=_on_stdout)
                result = project_run(
                    backend=backend,
                    model_path=self._model_path.resolve(),
                    script=self._script_path.resolve(),
                    **self._script_kwargs,
                )

            if result.get("status") == "ok":
                self._emit({"type": "agent_completed", "agent": self._name, "status": "success"})
                return {
                    "status": "success",
                    "result": result,
                    "stdout_lines": collected_lines,
                }
            else:
                self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
                return {
                    "status": "error",
                    "error": result.get("message", "Unknown error from ANSA backend"),
                    "result": result,
                    "stdout_lines": collected_lines,
                }
        except Exception as exc:
            self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
            return {
                "status": "error",
                "error": str(exc),
                "stdout_lines": collected_lines,
            }
