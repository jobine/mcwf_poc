import json
import asyncio
from typing import Dict, Set, List
from fastapi import WebSocket, WebSocketDisconnect, APIRouter

websocket_router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # experiment_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # experiment_id -> list of buffered events (for events sent before connection)
        self.event_buffer: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, experiment_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if experiment_id not in self.active_connections:
                self.active_connections[experiment_id] = set()
            self.active_connections[experiment_id].add(websocket)

            # Send any buffered events
            if experiment_id in self.event_buffer:
                for event in self.event_buffer[experiment_id]:
                    try:
                        await websocket.send_text(json.dumps(event))
                    except Exception:
                        pass
                # Clear the buffer after sending
                del self.event_buffer[experiment_id]

    async def disconnect(self, websocket: WebSocket, experiment_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if experiment_id in self.active_connections:
                self.active_connections[experiment_id].discard(websocket)
                if not self.active_connections[experiment_id]:
                    del self.active_connections[experiment_id]

    async def send_event(self, experiment_id: str, event: dict):
        """Send an event to all connections in a session, or buffer if no connections."""
        async with self._lock:
            if (
                experiment_id not in self.active_connections
                or not self.active_connections[experiment_id]
            ):
                # No active connections, buffer the event
                if experiment_id not in self.event_buffer:
                    self.event_buffer[experiment_id] = []
                self.event_buffer[experiment_id].append(event)
                return

        message = json.dumps(event)
        disconnected = set()

        for websocket in self.active_connections[experiment_id]:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.add(websocket)

        # Clean up disconnected sockets
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self.active_connections[experiment_id].discard(ws)

    async def broadcast(self, event: dict):
        """Broadcast an event to all connected sessions."""
        message = json.dumps(event)
        for experiment_id in list(self.active_connections.keys()):
            for websocket in list(self.active_connections.get(experiment_id, [])):
                try:
                    await websocket.send_text(message)
                except Exception:
                    pass


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager


@websocket_router.websocket("/ws/{experiment_id}")
async def websocket_endpoint(websocket: WebSocket, experiment_id: str):
    """
    WebSocket endpoint for real-time updates.

    Clients connect with a experiment_id and receive events for that session.
    """
    await manager.connect(websocket, experiment_id)

    try:
        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "experiment_id": experiment_id,
                "message": "Connected to StoryTeller WebSocket",
            }
        )

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages (mainly for keep-alive pings)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,  # 30 second timeout
                )

                # Handle ping/pong for keep-alive
                if data == "ping":
                    await websocket.send_text("pong")
                else:
                    # Echo back received messages (for debugging)
                    await websocket.send_json(
                        {
                            "type": "echo",
                            "data": data,
                        }
                    )

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket, experiment_id)
