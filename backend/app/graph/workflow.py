"""LangGraph workflow — orchestrates agent nodes into an executable graph.

Usage::

    from app.graph.workflow import create_ansa_workflow, run_workflow

    # Compile and invoke in one step
    state = run_workflow()

    # Or compile once, invoke many times
    workflow = create_ansa_workflow()
    state = workflow.invoke({...})
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from app.agents.ansa_agent import AnsaAgent
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
        """Create the experiment directory and emit workflow_init event."""
        exp_id = state["experiment_id"]
        exp_dir = settings.experiments_dir / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        if on_event:
            on_event({"type": "workflow_started", "experiment_id": exp_id})
        return {}
    return execute


def deinit_experiment(on_event: Callable[[dict], None] | None = None) -> Callable[[AnsaAgentState], AnsaAgentState]:
    """Create the deinit_experiment node function with event emission."""
    def execute(state: AnsaAgentState) -> AnsaAgentState:
        """Persist the workflow result and stdout log to the experiment directory."""
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

        if on_event:
            on_event({"type": "workflow_completed", **payload})
        return {}
    
    return execute


# ── Node factory ────────────────────────────────────────────────────

def create_classifier_node(
    on_event: Callable[[dict], None] | None = None,
) -> tuple[str, Callable]:
    """Build the classifier agent node from graph.json config.

    Returns (node_name, node_function).
    """
    classifier_cfg = _find_agent_config(cfg=_load_graph_config(), name="classifier")

    agent_node = AnsaAgent(
        name=classifier_cfg["name"],
        model_path=settings.data_shared_dir / classifier_cfg["model_path"],
        script_path=settings.scripts_dir / classifier_cfg["script_path"],
        script_kwargs=classifier_cfg.get("script_kwargs"),
        on_event=on_event,
    )

    return agent_node


# ── Graph construction ──────────────────────────────────────────────

def create_ansa_workflow(
    on_event: Callable[[dict], None] | None = None,
) -> StateGraph:
    """Build and compile the LangGraph workflow.

    Agent configuration (name, model_path, script_path, script_kwargs) is
    read from ``graph.json`` and looked up by *agent_name*.  Paths in the
    config are resolved using directory settings from ``.env``.

    Args:
        on_event: Optional callback invoked for workflow events (stdout,
            agent lifecycle, etc.). Each event is a dict with a ``type`` key.

    Graph::

        START ─► init_experiment ─► classifier ─► deinit_workflow ─► END
    """
    classifier_node = create_classifier_node(on_event=on_event)

    graph = StateGraph(AnsaAgentState)

    graph.add_node("init_experiment", init_experiment(on_event))
    graph.add_node(classifier_node.name, classifier_node.execute, retry=RetryPolicy(max_attempts=3))
    graph.add_node("deinit_workflow", deinit_experiment(on_event))

    graph.add_edge(START, "init_experiment")
    graph.add_edge("init_experiment", classifier_node.name)
    graph.add_edge(classifier_node.name, "deinit_workflow")
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
