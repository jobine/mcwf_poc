"""Workflow routes — REST endpoint to start workflows + WebSocket for stdout streaming.

Architecture:
    POST /workflow              → starts the workflow in background, returns experiment_id immediately
    WS   /workflow/{id}/stdout  → streams real-time ANSA stdout + heartbeat; bidirectional for future HITL
    GET  /workflow/{id}         → poll final result (optional convenience endpoint)
"""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.graph.workflow import create_ansa_workflow

router = APIRouter()

# ── In-memory workflow registry ─────────────────────────────────────
# Maps experiment_id → {"stdout_q": Queue, "future": Future, "state": dict | None}
_experiments: dict[str, dict] = {}

# Heartbeat interval (seconds) — keeps proxies / LBs from killing idle connections.
_HEARTBEAT_INTERVAL = 15


# ── Helpers ─────────────────────────────────────────────────────────

async def _send_json(ws: WebSocket, event: str, data: str | dict) -> None:
    """Send a JSON-encoded message with a standard envelope."""
    await ws.send_json({"event": event, "data": data})


def _run_workflow(experiment_id: str, stdout_q: queue.Queue) -> None:
    """Execute the workflow synchronously (called via run_in_executor)."""
    def _on_stdout(line: str) -> None:
        stdout_q.put(line)

    workflow = create_ansa_workflow(on_stdout=_on_stdout)
    final_state = workflow.invoke({
        "experiment_id": experiment_id,
        "status": "pending",
        "result": None,
        "error": None,
        "stdout_lines": [],
    })

    # Store final state and signal completion.
    _experiments[experiment_id]["state"] = final_state
    stdout_q.put(None)  # sentinel


# ── POST /experiment ──────────────────────────────────────────────────

@router.post("/experiment")
async def start_workflow():
    """Start an ANSA workflow in the background.

    Returns immediately with ``{"experiment_id": "..."}`` so the client
    can open a WebSocket on ``/experiment/{id}/stdout`` for live streaming.
    """
    stdout_q: queue.Queue[str | None] = queue.Queue()

    import uuid
    experiment_id = uuid.uuid4().hex

    loop = asyncio.get_running_loop()

    entry = {"stdout_q": stdout_q, "future": None, "state": None}
    _experiments[experiment_id] = entry

    future = loop.run_in_executor(None, _run_workflow, experiment_id, stdout_q)
    entry["future"] = future

    return JSONResponse({"experiment_id": experiment_id}, status_code=202)


# ── GET /experiment/{id} ──────────────────────────────────────────────

@router.get("/experiment/{experiment_id}")
async def get_workflow_result(experiment_id: str):
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


# ── WS /experiment/{id}/stdout ────────────────────────────────────────

@router.websocket("/experiment/{experiment_id}/stdout")
async def workflow_stdout_ws(ws: WebSocket, experiment_id: str):
    """Stream real-time ANSA stdout for a running workflow.

    **Server → Client messages** (JSON ``{"event": ..., "data": ...}``)::

        {"event": "stdout",    "data": "<line>"}       — real-time ANSA output
        {"event": "heartbeat", "data": ""}              — keep-alive ping
        {"event": "done",      "data": {…}}             — workflow finished, final state
        {"event": "error",     "data": "<message>"}     — unrecoverable error

    **Client → Server messages** (reserved for future Human-in-the-loop)::

        {"action": "cancel"}                   — request graceful cancellation  (not yet)
        {"action": "input", "payload": ...}    — HITL reply  (not yet)

    Example client (JavaScript)::

        // 1. Start workflow
        const resp = await fetch("/experiment", { method: "POST" });
        const { experiment_id } = await resp.json();

        // 2. Connect stdout stream
        const ws = new WebSocket(`ws://host/experiment/${experiment_id}/stdout`);
        ws.onmessage = (ev) => {
            const msg = JSON.parse(ev.data);
            if (msg.event === "stdout") console.log(msg.data);
            if (msg.event === "done")  { console.log(msg.data); ws.close(); }
        };
    """
    entry = _experiments.get(experiment_id)
    if entry is None:
        await ws.close(code=4004, reason="unknown experiment_id")
        return

    await ws.accept()
    stdout_q: queue.Queue[str | None] = entry["stdout_q"]

    try:
        seconds_since_last_send = 0.0
        poll_interval = 0.05

        while True:
            # Drain stdout queue
            drained = False
            while True:
                try:
                    line = stdout_q.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    # Sentinel — workflow finished
                    final = entry.get("state")
                    await _send_json(ws, "done", json.dumps(final, default=str) if final else "")
                    return
                await _send_json(ws, "stdout", line)
                seconds_since_last_send = 0.0
                drained = True

            if not drained:
                seconds_since_last_send += poll_interval
                if seconds_since_last_send >= _HEARTBEAT_INTERVAL:
                    await _send_json(ws, "heartbeat", "")
                    seconds_since_last_send = 0.0

            await asyncio.sleep(poll_interval)

    except WebSocketDisconnect:
        pass  # Client left — workflow continues in background
    except Exception as exc:
        try:
            await _send_json(ws, "error", str(exc))
        except WebSocketDisconnect:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
