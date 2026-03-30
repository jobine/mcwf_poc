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

def init_experiment(state: AnsaAgentState) -> AnsaAgentState:
    """Create the experiment directory for the given experiment_id."""
    exp_id = state["experiment_id"]
    exp_dir = settings.experiments_dir / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    return {}


def save_results(state: AnsaAgentState) -> AnsaAgentState:
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

    return {}


# ── Graph construction ──────────────────────────────────────────────

def create_ansa_workflow(
    on_stdout: Callable[[str], None] | None = None,
) -> StateGraph:
    """Build and compile the LangGraph workflow.

    Agent configuration (name, model_path, script_path, script_kwargs) is
    read from ``graph.json`` and looked up by *agent_name*.  Paths in the
    config are resolved using directory settings from ``.env``.

    Args:
        on_stdout: Optional callback invoked for every ANSA stdout line.
            Used by the API layer to push lines over WebSocket.

    Graph (with default agent name *classifier*)::

        START ─► init_experiment ─► validate_classifier_inputs ─┬─► run_classifier ─► save_results ─► END
                                                                └─► save_results ─► END
    """
    classifier_cfg = _find_agent_config(cfg=_load_graph_config(), name="classifier")

    agent = AnsaAgent(
        name=classifier_cfg["name"],
        model_path=settings.data_shared_dir / classifier_cfg["model_path"],
        script_path=settings.scripts_dir / classifier_cfg["script_path"],
        script_kwargs=classifier_cfg.get("script_kwargs", {}),
        on_stdout=on_stdout,
    )

    graph = StateGraph(AnsaAgentState)

    graph.add_node("init_experiment", init_experiment)
    graph.add_node(agent.validate_node_name, agent.validate_inputs)
    graph.add_node(agent.run_node_name, agent.run_ansa, retry=RetryPolicy(max_attempts=3))
    graph.add_node("save_results", save_results)

    graph.add_edge(START, "init_experiment")
    graph.add_edge("init_experiment", agent.validate_node_name)
    graph.add_conditional_edges(
        agent.validate_node_name,
        agent.should_run,
        {agent.run_node_name: agent.run_node_name, "end": "save_results"},
    )
    graph.add_edge(agent.run_node_name, "save_results")
    graph.add_edge("save_results", END)

    return graph.compile()


# ── Convenience runners ─────────────────────────────────────────────

def run_workflow(experiment_id: str | None = None) -> AnsaAgentState:
    """One-shot helper: build the workflow, invoke it, and return final state."""
    import uuid
    workflow = create_ansa_workflow(on_stdout=lambda line: print(f"[ANSA] {line}"))
    return workflow.invoke({
        "experiment_id": experiment_id or uuid.uuid4().hex,
        "status": "pending",
        "result": None,
        "error": None,
        "stdout_lines": [],
    })


async def arun_workflow() -> AnsaAgentState:
    """Async version of :func:`run_workflow`."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_workflow)


if __name__ == "__main__":
    final_state = run_workflow()
    print("Final state:", json.dumps(final_state, indent=2, default=str))
