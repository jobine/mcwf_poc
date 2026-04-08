"""Workflow routes — REST + WebSocket endpoints for workflow execution.

Architecture:
    GET  /workflow                  → compiled workflow graph as JSON
    GET  /experiments               → list all experiment IDs (newest first)
    POST /experiments               → start workflow (legacy), returns experiment_id
    POST /experiments/stream        → start workflow with event streaming, returns experiment_id
    GET  /experiments/{id}          → poll final result
    GET  /experiments/{id}/log      → stream real-time events
    WS   /experiments/{id}/stream   → real-time event stream (stdout, agent lifecycle, etc.)
    GET  /experiments/{id}/
"""

from __future__ import annotations

import asyncio
import json
import queue
import uuid

from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.config import settings
from app.graph.workflow import create_ansa_workflow

router = APIRouter()

# ── In-memory workflow registry ─────────────────────────────────────
# Maps experiment_id → {"event_q": Queue | None, "future": Future, "state": dict | None}
_experiments: dict[str, dict] = {}

# Heartbeat interval (seconds) — keeps proxies / LBs from killing idle connections.
_HEARTBEAT_INTERVAL = 15


# ── Workflow runners ─────────────────────────────────────────────────

def _run_workflow(experiment_id: str) -> None:
    """Execute the workflow synchronously (called via run_in_executor).

    Legacy runner — no event streaming.
    """
    workflow = create_ansa_workflow(on_event=lambda event: print(f"[EVENT] {event}"))
    final_state = workflow.invoke({
        "experiment_id": experiment_id,
        "status": "pending",
        "result": None,
        "error": None,
        "stdout_lines": [],
        "stderr_lines": [],
    })

    _experiments[experiment_id]["state"] = final_state


def _run_workflow_with_events(experiment_id: str, event_q: queue.Queue) -> None:
    """Execute the workflow synchronously with event streaming.

    All events (agent lifecycle, stdout) are pushed into *event_q* for the
    WebSocket handler. Events are also recorded to ``events.jsonl`` for replay.
    """
    recorded_events: list[dict] = []

    def _on_event(event: dict) -> None:
        recorded_events.append(event)
        event_q.put(event)

    try:
        workflow = create_ansa_workflow(on_event=_on_event)
        final_state = workflow.invoke({
            "experiment_id": experiment_id,
            "status": "pending",
            "result": None,
            "error": None,
            "stdout_lines": [],
        })

        _experiments[experiment_id]["state"] = final_state
    except Exception as exc:
        error_event = {"type": "error", "data": str(exc)}
        recorded_events.append(error_event)
        event_q.put(error_event)
    finally:
        event_q.put(None)  # sentinel

        # Persist events for replay
        exp_dir = settings.experiments_dir / experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "events.jsonl").write_text(
            "\n".join(json.dumps(e, default=str, ensure_ascii=False) for e in recorded_events) + "\n",
            encoding="utf-8",
        )


# ── GET /experiments ──────────────────────────────────────────────────

@router.get("/experiments")
async def list_experiments():
    """List all experiment IDs, sorted by creation time (newest first)."""
    exp_dir = settings.experiments_dir
    if not exp_dir.exists():
        return JSONResponse([])

    dirs = [d for d in exp_dir.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.stat().st_birthtime, reverse=True)
    return JSONResponse([{"experiment_id": d.name, "created_at": d.stat().st_birthtime} for d in dirs])


# ── GET /workflow ──────────────────────────────────────────────────────

@router.get("/workflow")
async def get_workflow_graph():
    """Return the compiled ANSA workflow graph as JSON."""
    workflow = create_ansa_workflow()
    return JSONResponse(workflow.get_graph().to_json())


# ── POST /experiments ──────────────────────────────────────────────────

@router.post("/experiments")
async def start_experiment():
    """Start an ANSA workflow in the background (legacy endpoint).

    Returns immediately with ``{"experiment_id": "..."}``.
    Use ``GET /experiments/{id}`` to poll for results.
    """
    experiment_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()

    entry = {"event_q": None, "future": None, "state": None}
    _experiments[experiment_id] = entry

    future = loop.run_in_executor(None, _run_workflow, experiment_id)
    entry["future"] = future

    return JSONResponse({"experiment_id": experiment_id}, status_code=202)


# ── POST /experiments/stream ──────────────────────────────────────────

@router.post("/experiments/stream")
async def start_experiment_stream():
    """Start an ANSA workflow with event streaming.

    Returns ``{"experiment_id": "..."}`` (202). Connect to
    ``WS /experiments/{id}/stream`` for real-time events.
    """
    event_q: queue.Queue[dict | None] = queue.Queue()
    experiment_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()

    entry = {"event_q": event_q, "future": None, "state": None}
    _experiments[experiment_id] = entry

    future = loop.run_in_executor(None, _run_workflow_with_events, experiment_id, event_q)
    entry["future"] = future

    return JSONResponse({"experiment_id": experiment_id}, status_code=202)


# ── GET /experiments/{id} ──────────────────────────────────────────────

@router.get("/experiments/{experiment_id}")
async def get_experiment_status(experiment_id: str):
    """Poll for the final workflow result.

    Returns 200 with the result when done, 202 while still running,
    or 404 if the experiment_id is unknown.
    """
    entry = _experiments.get(experiment_id)
    if entry is None:
        return JSONResponse({"error": "unknown experiment_id"}, status_code=404)

    if entry["state"] is not None:
        return JSONResponse(entry["state"])

    return JSONResponse({"status": "running"}, status_code=202)


# ── GET /experiments/{id}/log ──────────────────────────────────────────

@router.get("/experiments/{experiment_id}/log")
async def get_experiment_log(experiment_id: str):
    """Return the recorded events for an experiment.

    Reads ``events.jsonl`` from the experiment directory and returns the
    list of event objects.  Returns 404 if the experiment directory or
    the log file does not exist.
    """
    events_file: Path = settings.experiments_dir / experiment_id / "events.jsonl"
    if not events_file.exists():
        return JSONResponse({"error": "experiment log not found"}, status_code=404)

    events = [
        json.loads(line)
        for line in events_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return JSONResponse(events)


# ── WS /experiments/{id}/stream ────────────────────────────────────────

@router.websocket("/experiments/{experiment_id}/stream")
async def experiment_stream_ws(ws: WebSocket, experiment_id: str):
    """Stream real-time workflow events over WebSocket.

    **Server → Client messages** (JSON with ``type`` field)::

        {"type": "workflow_started",  "data": {"experiment_id": "..."}}
        {"type": "agent_started",     "agent": "..."}
        {"type": "stdout",            "data": "<plain text line>"}
        {"type": "agent_completed",   "agent": "...", "status": "..."}
        {"type": "workflow_completed", "data": {<final_state>}}
        {"type": "error",             "data": "<message>"}
        {"type": "heartbeat",         "data": ""}

    **Client → Server messages** (reserved for future Human-in-the-loop)::

        {"action": "cancel"}                   — request graceful cancellation  (not yet)
        {"action": "input", "payload": ...}    — HITL reply  (not yet)
    """
    entry = _experiments.get(experiment_id)
    if entry is None or entry.get("event_q") is None:
        await ws.close(code=4004, reason="unknown experiment_id or no event stream")
        return

    await ws.accept()
    event_q: queue.Queue[dict | None] = entry["event_q"]

    try:
        seconds_since_last_send = 0.0
        poll_interval = 0.05

        while True:
            # Drain event queue
            drained = False
            while True:
                try:
                    event = event_q.get_nowait()
                except queue.Empty:
                    break
                if event is None:
                    # Sentinel — workflow finished
                    return
                await ws.send_json(event)
                seconds_since_last_send = 0.0
                drained = True

            if not drained:
                seconds_since_last_send += poll_interval
                if seconds_since_last_send >= _HEARTBEAT_INTERVAL:
                    await ws.send_json({"type": "heartbeat", "data": ""})
                    seconds_since_last_send = 0.0

            await asyncio.sleep(poll_interval)

    except WebSocketDisconnect:
        pass  # Client left — workflow continues in background
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "data": str(exc)})
        except WebSocketDisconnect:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
