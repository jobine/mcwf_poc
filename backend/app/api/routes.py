"""Workflow routes — exposes workflow execution over WebSocket.

Supports long-running workflows with heartbeat keep-alive and
bidirectional messaging (ready for future Human-in-the-loop agents).
"""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.graph.workflow import create_ansa_workflow

router = APIRouter()

# Heartbeat interval (seconds) — keeps proxies / LBs from killing idle connections.
_HEARTBEAT_INTERVAL = 15


# ── Helpers ─────────────────────────────────────────────────────────

async def _send_json(ws: WebSocket, event: str, data: str | dict) -> None:
    """Send a JSON-encoded message with a standard envelope."""
    await ws.send_json({"event": event, "data": data})


# ── WS /workflow ────────────────────────────────────────────────────

@router.websocket("/workflow")
async def workflow_ws(ws: WebSocket):
    """Run an ANSA workflow, streaming events over WebSocket.

    **Server → Client messages** (JSON ``{"event": ..., "data": ...}``)::

        {"event": "stdout",    "data": "<line>"}       — real-time ANSA output
        {"event": "heartbeat", "data": ""}              — keep-alive ping
        {"event": "result",    "data": {…}}             — final workflow state
        {"event": "error",     "data": "<message>"}     — unrecoverable error

    **Client → Server messages** (reserved for future use)::

        {"action": "cancel"}   — request graceful cancellation  (not yet implemented)
        {"action": "input", "payload": ...}  — human-in-the-loop reply  (not yet implemented)

    Example client (JavaScript)::

        const ws = new WebSocket("ws://localhost:8000/workflow");
        ws.onmessage = (ev) => {
            const msg = JSON.parse(ev.data);
            if (msg.event === "stdout")  console.log(msg.data);
            if (msg.event === "result")  { console.log(msg.data); ws.close(); }
        };
    """
    await ws.accept()

    stdout_q: queue.Queue[str | None] = queue.Queue()

    def _on_stdout(line: str) -> None:
        stdout_q.put(line)

    loop = asyncio.get_running_loop()
    workflow = create_ansa_workflow(on_stdout=_on_stdout)
    future = loop.run_in_executor(None, workflow.invoke, {
        "status": "pending",
        "result": None,
        "error": None,
        "stdout_lines": [],
    })

    try:
        seconds_since_last_send = 0.0
        poll_interval = 0.05

        while not future.done():
            # Drain stdout queue
            drained = False
            while True:
                try:
                    line = stdout_q.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    break
                await _send_json(ws, "stdout", line)
                seconds_since_last_send = 0.0
                drained = True

            if not drained:
                seconds_since_last_send += poll_interval
                if seconds_since_last_send >= _HEARTBEAT_INTERVAL:
                    await _send_json(ws, "heartbeat", "")
                    seconds_since_last_send = 0.0

            await asyncio.sleep(poll_interval)

        final_state = await future

        # Flush remaining stdout
        while not stdout_q.empty():
            line = stdout_q.get_nowait()
            if line is not None:
                await _send_json(ws, "stdout", line)

        await _send_json(ws, "result", json.dumps(final_state, default=str))

    except WebSocketDisconnect:
        # Client went away — cancel the background workflow if still running.
        future.cancel()
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
