# Shared AnsaProcess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow multiple AnsaAgents to share a single AnsaProcess via a workflow-level registry, so agents like cleaner can operate on the same in-memory model loaded by classifier.

**Architecture:** A `ProcessRegistry` holds live `AnsaProcess` instances keyed by `process_id`. Agents check state for an existing `process_id` — if found, reuse the process from the registry; if not, create a new one and register it. `deinit_experiment` shuts down all registered processes.

**Tech Stack:** Python 3.12, LangGraph, pytest, unittest.mock

---

### Task 1: Add `process_id` to AnsaAgentState

**Files:**
- Modify: `backend/app/graph/state.py:8-17`
- Test: `backend/tests/graph/test_state.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/graph/__init__.py` (empty) and `backend/tests/graph/test_state.py`:

```python
"""Tests for AnsaAgentState type definition."""

from app.graph.state import AnsaAgentState


class TestAnsaAgentState:
    def test_process_id_field_accepted(self):
        """process_id should be an accepted optional field."""
        state: AnsaAgentState = {
            "experiment_id": "abc",
            "status": "pending",
            "process_id": "p0",
        }
        assert state["process_id"] == "p0"

    def test_process_id_defaults_absent(self):
        """State without process_id should still be valid (total=False)."""
        state: AnsaAgentState = {
            "experiment_id": "abc",
            "status": "pending",
        }
        assert "process_id" not in state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && poetry run pytest tests/graph/test_state.py -v`
Expected: FAIL — `process_id` is not a recognized key in the TypedDict

- [ ] **Step 3: Add `process_id` field to state**

In `backend/app/graph/state.py`, add the field to `AnsaAgentState`:

```python
class AnsaAgentState(TypedDict, total=False):
    """State carried through the ANSA workflow graph."""
    experiment_id: str
    model_path: str
    script_path: str
    status: str
    result: dict | None
    error: str | None
    stdout_lines: list[str]
    stderr_lines: list[str]
    process_id: str | None  # key into ProcessRegistry for shared ANSA processes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && poetry run pytest tests/graph/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to check for regressions**

Run: `cd backend && poetry run pytest tests/ -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/graph/state.py tests/graph/__init__.py tests/graph/test_state.py
git commit -m "feat: add process_id field to AnsaAgentState for process sharing"
```

---

### Task 2: Create ProcessRegistry

**Files:**
- Create: `backend/app/agents/process_registry.py`
- Test: `backend/tests/agents/__init__.py` (create)
- Test: `backend/tests/agents/test_process_registry.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/agents/__init__.py` (empty) and `backend/tests/agents/test_process_registry.py`:

```python
"""Tests for ProcessRegistry."""

from unittest.mock import MagicMock

import pytest

from app.agents.process_registry import ProcessRegistry


class TestProcessRegistry:
    def test_get_returns_none_for_unknown_key(self):
        registry = ProcessRegistry()
        assert registry.get("unknown") is None

    def test_register_and_get(self):
        registry = ProcessRegistry()
        mock_proc = MagicMock()
        registry.register("p0", mock_proc)
        assert registry.get("p0") is mock_proc

    def test_register_overwrites_existing(self):
        registry = ProcessRegistry()
        mock_proc_1 = MagicMock()
        mock_proc_2 = MagicMock()
        registry.register("p0", mock_proc_1)
        registry.register("p0", mock_proc_2)
        assert registry.get("p0") is mock_proc_2

    def test_shutdown_all_calls_shutdown_on_each(self):
        registry = ProcessRegistry()
        procs = [MagicMock() for _ in range(3)]
        for i, p in enumerate(procs):
            registry.register(f"p{i}", p)
        registry.shutdown_all()
        for p in procs:
            p.shutdown.assert_called_once()

    def test_shutdown_all_clears_registry(self):
        registry = ProcessRegistry()
        registry.register("p0", MagicMock())
        registry.shutdown_all()
        assert registry.get("p0") is None

    def test_shutdown_all_ignores_exceptions(self):
        registry = ProcessRegistry()
        bad_proc = MagicMock()
        bad_proc.shutdown.side_effect = RuntimeError("boom")
        good_proc = MagicMock()
        registry.register("p0", bad_proc)
        registry.register("p1", good_proc)
        registry.shutdown_all()  # should not raise
        good_proc.shutdown.assert_called_once()

    def test_next_id_auto_increments(self):
        registry = ProcessRegistry()
        assert registry.next_id() == "p0"
        assert registry.next_id() == "p1"
        assert registry.next_id() == "p2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && poetry run pytest tests/agents/test_process_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement ProcessRegistry**

Create `backend/app/agents/process_registry.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && poetry run pytest tests/agents/test_process_registry.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/agents/process_registry.py tests/agents/__init__.py tests/agents/test_process_registry.py
git commit -m "feat: add ProcessRegistry for shared AnsaProcess management"
```

---

### Task 3: Refactor AnsaAgent to use ProcessRegistry

**Files:**
- Modify: `backend/app/agents/ansa_agent.py`
- Create: `backend/tests/agents/test_ansa_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/agents/test_ansa_agent.py`:

```python
"""Tests for AnsaAgent with ProcessRegistry support."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.ansa_agent import AnsaAgent
from app.agents.process_registry import ProcessRegistry


def _make_agent(name="test_agent", model_path=None, script_path=None, registry=None, on_event=None):
    """Helper to build an AnsaAgent with mocked paths."""
    return AnsaAgent(
        name=name,
        model_path=model_path,
        script_path=script_path,
        registry=registry,
        on_event=on_event,
    )


class TestAnsaAgentCreatesProcess:
    """When no process_id in state, agent creates a new AnsaProcess."""

    @patch("app.agents.ansa_agent.open_model")
    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_creates_process_and_registers(self, MockProcess, mock_open_model):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}
        mock_open_model.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(
            model_path=model_path,
            script_path=script_path,
            registry=registry,
        )
        result = agent.execute({"status": "pending"})

        # Process was created and registered
        assert result["process_id"] is not None
        assert registry.get(result["process_id"]) is mock_backend
        # Process was connected and output readers started
        mock_backend.connect.assert_called_once()
        mock_backend.start_output_reader.assert_called_once()
        # Model was opened
        mock_open_model.assert_called_once()

    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_creates_process_without_model_path(self, MockProcess):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending"})

        assert result["process_id"] is not None
        assert result["status"] == "success"


class TestAnsaAgentReusesProcess:
    """When process_id exists in state and registry, agent reuses it."""

    def test_reuses_existing_process(self):
        mock_backend = MagicMock()
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        registry.register("p0", mock_backend)

        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending", "process_id": "p0"})

        assert result["process_id"] == "p0"
        assert result["status"] == "success"
        # Should NOT have created a new process
        mock_backend.run_script.assert_called_once()

    @patch("app.agents.ansa_agent.open_model")
    def test_reuses_process_and_opens_model(self, mock_open_model):
        mock_backend = MagicMock()
        mock_backend.run_script.return_value = {"success": True}
        mock_open_model.return_value = {"success": True}

        registry = ProcessRegistry()
        registry.register("p0", mock_backend)

        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(
            model_path=model_path,
            script_path=script_path,
            registry=registry,
        )
        result = agent.execute({"status": "pending", "process_id": "p0"})

        assert result["process_id"] == "p0"
        mock_open_model.assert_called_once()


class TestAnsaAgentErrorHandling:
    def test_missing_script_file(self):
        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = False
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(model_path=model_path, script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending"})
        assert result["status"] == "error"

    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_process_id_in_state_but_not_in_registry(self, MockProcess):
        """If process_id references a dead process, create a new one."""
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending", "process_id": "dead_id"})

        # Should create a new process since "dead_id" is not in registry
        assert result["process_id"] != "dead_id"
        assert result["status"] == "success"


class TestAnsaAgentEvents:
    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_emits_lifecycle_events(self, MockProcess):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        events = []
        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(
            script_path=script_path,
            registry=registry,
            on_event=events.append,
        )
        agent.execute({"status": "pending"})

        event_types = [e["type"] for e in events]
        assert "agent_started" in event_types
        assert "agent_completed" in event_types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && poetry run pytest tests/agents/test_ansa_agent.py -v`
Expected: FAIL — `registry` is not an accepted parameter

- [ ] **Step 3: Refactor AnsaAgent**

Replace the contents of `backend/app/agents/ansa_agent.py`:

```python
"""ANSA agent — manages ANSA-related workflow nodes.

Provides :class:`AnsaAgent` whose :meth:`execute` method serves as a
LangGraph node function that validates inputs, launches ANSA, and runs a script.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from app.core.ansa_backend import _backend_result_error
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
        script_kwargs: str | None = None,
        registry: ProcessRegistry | None = None,
        on_event: Callable[[dict], None] | None = None,
    ):
        self._name = name
        self._model_path = Path(model_path) if model_path else None
        self._script_path = Path(script_path) if script_path else None
        self._script_kwargs = ast.literal_eval(script_kwargs) if script_kwargs else {}
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
        if self._script_path and not self._script_path.is_file():
            errors.append(f"Script file not found: {self._script_path}")

        if errors:
            error_msg = "; ".join(errors)
            self._emit({"type": "agent_completed", "agent": self._name, "status": "error"})
            return {"status": "error", "error": error_msg}

        # ── resolve or create ANSA process ─────────────────────────
        from app.core.ansa_backend import AnsaProcess, _is_backend_result_ok
        from app.core.project import open_model

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
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `cd backend && poetry run pytest tests/agents/test_ansa_agent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run all tests to check for regressions**

Run: `cd backend && poetry run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/agents/ansa_agent.py tests/agents/test_ansa_agent.py
git commit -m "feat: refactor AnsaAgent to create/reuse processes via ProcessRegistry"
```

---

### Task 4: Update workflow to create registry and pass to agents/deinit

**Files:**
- Modify: `backend/app/graph/workflow.py`
- Create: `backend/tests/graph/test_workflow.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/graph/test_workflow.py`:

```python
"""Tests for workflow integration with ProcessRegistry."""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.process_registry import ProcessRegistry


class TestWorkflowRegistry:
    """Verify that create_ansa_workflow passes a registry to agents and deinit."""

    @patch("app.graph.workflow._load_graph_config")
    def test_agents_receive_shared_registry(self, mock_config):
        mock_config.return_value = {
            "agents": [
                {"name": "classifier", "type": "AnsaAgent", "model_path": "m.ansa", "script_path": "s.py"},
                {"name": "cleaner", "type": "AnsaAgent", "script_path": "c.py"},
            ]
        }

        from app.graph.workflow import create_classifier_node, create_cleaner_node

        registry = ProcessRegistry()
        classifier = create_classifier_node(registry=registry)
        cleaner = create_cleaner_node(registry=registry)

        assert classifier._registry is registry
        assert cleaner._registry is registry


class TestDeinitShutdownsRegistry:
    """Verify deinit_experiment calls registry.shutdown_all()."""

    def test_deinit_shuts_down_registry(self):
        from app.graph.workflow import deinit_experiment

        registry = ProcessRegistry()
        mock_proc = MagicMock()
        registry.register("p0", mock_proc)

        deinit_fn = deinit_experiment(on_event=None, registry=registry)
        deinit_fn({
            "experiment_id": "test-exp",
            "status": "success",
            "result": None,
            "error": None,
            "stdout_lines": [],
            "stderr_lines": [],
        })

        mock_proc.shutdown.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && poetry run pytest tests/graph/test_workflow.py -v`
Expected: FAIL — `registry` parameter not accepted

- [ ] **Step 3: Update workflow.py**

Modify `backend/app/graph/workflow.py` — the key changes are:

1. `create_classifier_node` and `create_cleaner_node` accept `registry` and pass it to `AnsaAgent`
2. `deinit_experiment` accepts `registry` and calls `registry.shutdown_all()` at the end
3. `create_ansa_workflow` creates a `ProcessRegistry` and passes it everywhere

```python
"""LangGraph workflow — orchestrates agent nodes into an executable graph."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from app.agents.ansa_agent import AnsaAgent
from app.agents.process_registry import ProcessRegistry
from app.config import settings
from app.graph.state import AnsaAgentState


def _load_graph_config() -> dict:
    """Read and return the graph configuration from *graph.json*."""
    config_path = settings.graph_config_path
    with open(config_path, encoding="utf-8") as fh:
        return json.load(fh)


def _find_agent_config(cfg: dict, name: str) -> dict:
    """Look up an agent entry in *cfg* by *name*."""
    for entry in cfg.get("agents", []):
        if entry.get("name") == name:
            return entry
    available = [e.get("name") for e in cfg.get("agents", [])]
    raise ValueError(f"Agent {name!r} not found in graph.json (available: {available})")


# ── Experiment lifecycle nodes ──────────────────────────────────────

def init_experiment(on_event: Callable[[dict], None] | None = None):
    """Create the init_experiment node function with event emission."""
    def execute(state: AnsaAgentState) -> AnsaAgentState:
        exp_id = state["experiment_id"]
        exp_dir = settings.experiments_dir / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        if on_event:
            on_event({"type": "workflow_started", "experiment_id": exp_id})
        return {}
    return execute


def deinit_experiment(
    on_event: Callable[[dict], None] | None = None,
    registry: ProcessRegistry | None = None,
) -> Callable[[AnsaAgentState], AnsaAgentState]:
    """Create the deinit_experiment node function with event emission."""
    def execute(state: AnsaAgentState) -> AnsaAgentState:
        exp_id = state.get("experiment_id", "")
        exp_dir = settings.experiments_dir / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "experiment_id": exp_id,
            "status": state.get("status"),
            "result": state.get("result"),
            "error": state.get("error"),
        }
        (exp_dir / "result.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8",
        )

        stdout_lines = state.get("stdout_lines") or []
        if stdout_lines:
            (exp_dir / "stdout.log").write_text(
                "\n".join(stdout_lines) + "\n", encoding="utf-8",
            )

        stderr_lines = state.get("stderr_lines") or []
        if stderr_lines:
            (exp_dir / "stderr.log").write_text(
                "\n".join(stderr_lines) + "\n", encoding="utf-8",
            )

        # Shutdown all shared ANSA processes
        if registry:
            registry.shutdown_all()

        if on_event:
            on_event({"type": "workflow_completed", **payload})
        return {}

    return execute


# ── Node factory ────────────────────────────────────────────────────

def create_classifier_node(
    on_event: Callable[[dict], None] | None = None,
    registry: ProcessRegistry | None = None,
) -> AnsaAgent:
    """Build the classifier agent node from graph.json config."""
    classifier_cfg = _find_agent_config(cfg=_load_graph_config(), name="classifier")

    return AnsaAgent(
        name=classifier_cfg["name"],
        model_path=settings.data_shared_dir / classifier_cfg["model_path"],
        script_path=settings.scripts_dir / classifier_cfg["script_path"],
        script_kwargs=classifier_cfg.get("script_kwargs"),
        registry=registry,
        on_event=on_event,
    )


def create_cleaner_node(
    on_event: Callable[[dict], None] | None = None,
    registry: ProcessRegistry | None = None,
) -> AnsaAgent:
    """Build the cleaner agent node from graph.json config."""
    cleaner_cfg = _find_agent_config(cfg=_load_graph_config(), name="cleaner")

    return AnsaAgent(
        name=cleaner_cfg["name"],
        script_path=settings.scripts_dir / cleaner_cfg["script_path"],
        registry=registry,
        on_event=on_event,
    )


# ── Graph construction ──────────────────────────────────────────────

def create_ansa_workflow(
    on_event: Callable[[dict], None] | None = None,
) -> StateGraph:
    """Build and compile the LangGraph workflow.

    Graph::

        START -> init_experiment -> classifier -> cleaner -> deinit_workflow -> END
    """
    registry = ProcessRegistry()

    classifier_node = create_classifier_node(on_event=on_event, registry=registry)
    cleaner_node = create_cleaner_node(on_event=on_event, registry=registry)

    graph = StateGraph(AnsaAgentState)

    graph.add_node("init_experiment", init_experiment(on_event))
    graph.add_node(classifier_node.name, classifier_node.execute, retry=RetryPolicy(max_attempts=3))
    graph.add_node(cleaner_node.name, cleaner_node.execute, retry=RetryPolicy(max_attempts=3))
    graph.add_node("deinit_workflow", deinit_experiment(on_event, registry))

    graph.add_edge(START, "init_experiment")
    graph.add_edge("init_experiment", classifier_node.name)
    graph.add_edge(classifier_node.name, cleaner_node.name)
    graph.add_edge(cleaner_node.name, "deinit_workflow")
    graph.add_edge("deinit_workflow", END)

    return graph.compile()


# ── Convenience runners ─────────────────────────────────────────────

def run_workflow(experiment_id: str | None = None) -> AnsaAgentState:
    """One-shot helper: build the workflow, invoke it, and return final state."""
    import uuid
    workflow = create_ansa_workflow()
    return workflow.invoke({
        "experiment_id": experiment_id or uuid.uuid4().hex,
        "status": "pending",
        "result": None,
        "error": None,
        "stdout_lines": [],
        "stderr_lines": [],
    })


async def arun_workflow() -> AnsaAgentState:
    """Async version of :func:`run_workflow`."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_workflow)


if __name__ == "__main__":
    final_state = run_workflow()
    print("Final state:", json.dumps(final_state, indent=2, default=str))
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `cd backend && poetry run pytest tests/graph/test_workflow.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run all tests**

Run: `cd backend && poetry run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/graph/workflow.py tests/graph/test_workflow.py
git commit -m "feat: wire ProcessRegistry through workflow, agents, and deinit"
```

---

### Task 5: Final integration verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full test suite**

Run: `cd backend && poetry run pytest tests/ -v`
Expected: All tests PASS (state, registry, agent, workflow)

- [ ] **Step 2: Verify workflow graph compiles**

Run: `cd backend && poetry run python -c "from app.graph.workflow import create_ansa_workflow; w = create_ansa_workflow(); print('Graph compiled OK')"` 
Expected: "Graph compiled OK" (may fail if .env not configured — that's fine for CI)

- [ ] **Step 3: Commit any remaining fixes if needed**
