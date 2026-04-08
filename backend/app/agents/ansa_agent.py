"""ANSA agent — manages ANSA-related workflow nodes.

Provides :class:`AnsaAgent` whose :meth:`execute` method serves as a
LangGraph node function that validates inputs, launches ANSA, and runs a script.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from app.core.ansa_backend import AnsaProcess, _backend_result_error, _is_backend_result_ok
from app.core.project import open_model
from app.graph.state import AnsaAgentState

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.process_registry import ProcessRegistry


class AnsaAgent:
    """Encapsulates all ANSA-related logic for a single graph node.

    Args:
        name: Logical name for this agent (also used as the graph node name).
        model_path: Path to the ANSA model file. If set, open_model is called.
        script_path: Path to the Python script to execute.
        script_kwargs: Keyword arguments forwarded to ``project.run``.
        registry: Shared ProcessRegistry for creating/reusing ANSA processes.
        on_event: Optional callback invoked for workflow events.
    """

    def __init__(
        self,
        name: str,
        model_path: str | Path | None = None,
        script_path: str | Path | None = None,
        script_kwargs: str | dict | None = None,
        registry: ProcessRegistry | None = None,
        on_event: Callable[[dict], None] | None = None,
    ):
        self._name = name
        if model_path is None:
            self._model_path = None
        elif isinstance(model_path, Path):
            self._model_path = model_path
        else:
            self._model_path = Path(model_path)

        if script_path is None:
            self._script_path = None
        elif isinstance(script_path, Path):
            self._script_path = script_path
        else:
            self._script_path = Path(script_path)

        # script_kwargs can be a dict (from JSON) or a string (to be eval'd)
        if isinstance(script_kwargs, dict):
            self._script_kwargs = script_kwargs
        elif script_kwargs:
            self._script_kwargs = ast.literal_eval(script_kwargs)
        else:
            self._script_kwargs = {}
        self._registry = registry
        self._on_event = on_event

    @property
    def name(self) -> str:
        """Logical agent name (also used as the graph node name)."""
        return self._name

    def _emit(self, event: dict) -> None:
        if self._on_event is not None:
            self._on_event(event)

    def execute(self, state: AnsaAgentState) -> AnsaAgentState:
        """Validate inputs, then run the script on a shared or new ANSA process.

        Emits ``agent_started``, ``stdout``, and ``agent_completed`` events.
        """
        self._emit({"type": "agent_started", "agent": self._name})

        # ── validate inputs ────────────────────────────────────────
        errors: list[str] = []
        if self._model_path and not self._model_path.is_file():
            errors.append(f"Model file not found: {self._model_path}")
        if not self._script_path:
            errors.append("No script configured")
        elif not self._script_path.is_file():
            errors.append(f"Script file not found: {self._script_path}")

        if errors:
            error_msg = "; ".join(errors)
            self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
            return {"status": "error", "error": error_msg, "process_id": state.get("process_id")}

        # ── resolve or create ANSA process ─────────────────────────
        collected_stdout: list[str] = []
        collected_stderr: list[str] = []

        def _on_stdout(line: str) -> None:
            collected_stdout.append(line)
            print(f"[ANSA:out] {line}", flush=True)
            self._emit({"type": "stdout", "data": line})

        def _on_stderr(line: str) -> None:
            collected_stderr.append(line)
            print(f"[ANSA:err] {line}", flush=True)
            self._emit({"type": "stderr", "data": line})

        try:
            process_id = state.get("process_id")
            backend = None

            if process_id and self._registry:
                backend = self._registry.get(process_id)

            if backend is None:
                # Create new process and register it
                backend = AnsaProcess()
                backend.connect()
                backend.start_output_reader(on_stdout=_on_stdout, on_stderr=_on_stderr)
                if self._registry:
                    process_id = self._registry.next_id()
                    self._registry.register(process_id, backend)

            # ── open model if configured ───────────────────────────
            if self._model_path:
                model_result = open_model(backend=backend, model_path=self._model_path.resolve())
                if not _is_backend_result_ok(model_result):
                    self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
                    return {
                        "status": "error",
                        "error": _backend_result_error("Failed to open model", model_result),
                        "process_id": process_id,
                        "stdout_lines": collected_stdout,
                        "stderr_lines": collected_stderr,
                    }

            # ── run script ─────────────────────────────────────────
            script_result = backend.run_script(
                script=self._script_path,
                script_kwargs=self._script_kwargs,
            )
            if not _is_backend_result_ok(script_result):
                self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
                return {
                    "status": "error",
                    "error": _backend_result_error("Script execution failed", script_result),
                    "process_id": process_id,
                    "result": {"script_result": script_result},
                    "stdout_lines": collected_stdout,
                    "stderr_lines": collected_stderr,
                }

            self._emit({"type": "agent_completed", "agent": self._name, "status": "success"})
            return {
                "status": "success",
                "result": {"script_result": script_result},
                "process_id": process_id,
                "stdout_lines": collected_stdout,
                "stderr_lines": collected_stderr,
            }

        except Exception as exc:
            self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
            return {
                "status": "error",
                "error": str(exc),
                "process_id": state.get("process_id"),
                "stdout_lines": collected_stdout,
                "stderr_lines": collected_stderr,
            }
