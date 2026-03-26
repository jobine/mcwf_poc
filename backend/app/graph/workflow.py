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

from app.agents.ansa_agent import AnsaAgent
from app.config import settings
from app.graph.state import AnsaAgentState


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

    Args:
        model_path: Path to the ANSA model file. Defaults to demo.ansa.
        script_path: Path to the script to execute. Defaults to part_classifier.py.
        on_stdout: Optional callback invoked for every ANSA stdout line.
            Used by the API layer to push lines over WebSocket.

    Graph::

        START ─► init_experiment ─► validate_inputs ─┬─► run_ansa ─► save_results ─► END
                                                     └─► save_results ─► END
    """
    ansa = AnsaAgent(
        model_path=settings.data_shared_dir / "demo.ansa",
        script_path=settings.scripts_dir / "part_classifier.py",
        on_stdout=on_stdout,
    )

    graph = StateGraph(AnsaAgentState)

    graph.add_node("init_experiment", init_experiment)
    graph.add_node("validate_inputs", ansa.validate_inputs)
    graph.add_node("run_ansa", ansa.run_ansa)
    graph.add_node("save_results", save_results)

    graph.add_edge(START, "init_experiment")
    graph.add_edge("init_experiment", "validate_inputs")
    graph.add_conditional_edges(
        "validate_inputs",
        ansa.should_run,
        {"run_ansa": "run_ansa", "end": "save_results"},
    )
    graph.add_edge("run_ansa", "save_results")
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
