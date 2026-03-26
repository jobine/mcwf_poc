"""ANSA agent — manages ANSA-related workflow nodes.

Provides :class:`AnsaAgent` whose methods serve as LangGraph node
functions for validating inputs, launching ANSA, and running scripts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.graph.state import AnsaAgentState


class AnsaAgent:
    """Encapsulates all ANSA-related graph nodes.

    Each public method has the signature ``(state) -> state`` expected by
    LangGraph and can be registered directly as a graph node.

    Args:
        model_path: Path to the ANSA model file.
        script_path: Path to the Python script to execute.
        on_stdout: Optional extra callback invoked for every ANSA stdout
            line. Use this to push lines to an SSE queue, WebSocket, etc.
        **kwargs: Additional keyword arguments passed to ``project.run``.
    """

    def __init__(
        self,
        model_path: str | Path,
        script_path: str | Path,
        on_stdout: Callable[[str], None] | None = None,
        **kwargs,
    ):
        self._model_path = Path(model_path)
        self._script_path = Path(script_path)
        self._script_kwargs = kwargs

        self._on_stdout = on_stdout

    # ── nodes ───────────────────────────────────────────────────────

    def validate_inputs(self, state: AnsaAgentState) -> AnsaAgentState:
        """Validate that model and script paths exist."""
        model = self._model_path
        script = self._script_path

        errors: list[str] = []
        if not model.is_file():
            errors.append(f"Model file not found: {model}")
        if not script.is_file():
            errors.append(f"Script file not found: {script}")

        if errors:
            return {
                "status": "error",
                "error": "; ".join(errors),
            }

        return {
            "model_path": str(model.resolve()),
            "script_path": str(script.resolve()),
            "status": "running",
        }

    def run_ansa(self, state: AnsaAgentState) -> AnsaAgentState:
        """Open the model and execute the script via ``project.run``."""
        from app.core.ansa_backend import AnsaProcess
        from app.core.project import run as project_run

        collected_lines: list[str] = []
        external_cb = self._on_stdout

        def _on_stdout(line: str) -> None:
            collected_lines.append(line)
            print(f"[ANSA] {line}", flush=True)
            if external_cb is not None:
                external_cb(line)

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
                return {
                    "status": "success",
                    "result": result,
                    "stdout_lines": collected_lines,
                }
            else:
                return {
                    "status": "error",
                    "error": result.get("message", "Unknown error from ANSA backend"),
                    "result": result,
                    "stdout_lines": collected_lines,
                }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "stdout_lines": collected_lines,
            }

    # ── routing helpers ─────────────────────────────────────────────

    @staticmethod
    def should_run(state: AnsaAgentState) -> str:
        """Decide next step after validation."""
        if state.get("status") == "error":
            return "end"
        return "run_ansa"
