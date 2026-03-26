"""Workflow routes — exposes workflow execution over HTTP with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.graph.workflow import create_ansa_workflow

router = APIRouter()


# ── POST /workflow ──────────────────────────────────────────────────

@router.post("/workflow")
async def start_workflow():
    """Start an ANSA workflow and stream stdout lines via SSE.
    
    The response is an SSE stream with two event types:

    * **stdout** — one per ANSA stdout line (real-time)
    * **result** — single final event carrying the full workflow state

    Example client (JavaScript)::

        const es = new EventSource("/workflow", { method: "POST", ... });
        es.addEventListener("stdout", e => console.log(e.data));
        es.addEventListener("result", e => { console.log(JSON.parse(e.data)); es.close(); });
    """
    stdout_q: queue.Queue[str | None] = queue.Queue()

    def _on_stdout(line: str) -> None:
        stdout_q.put(line)

    async def _event_generator():
        loop = asyncio.get_running_loop()

        workflow = create_ansa_workflow(on_stdout=_on_stdout)
        future = loop.run_in_executor(None, workflow.invoke, {
            "status": "pending",
            "result": None,
            "error": None,
            "stdout_lines": [],
        })

        # Drain the queue while the workflow is running.
        while not future.done():
            try:
                line = stdout_q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if line is None:
                break
            yield {"event": "stdout", "data": line}

        final_state = await future

        # Flush remaining lines
        while not stdout_q.empty():
            line = stdout_q.get_nowait()
            if line is not None:
                yield {"event": "stdout", "data": line}

        yield {"event": "result", "data": json.dumps(final_state, default=str)}

    return EventSourceResponse(_event_generator())
