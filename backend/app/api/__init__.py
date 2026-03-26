"""API package — mounts all route modules on the FastAPI app."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="MCWF PoC", version="0.1.0", lifespan=lifespan)

# Register route modules
from app.api.routes import router  # noqa: E402

app.include_router(router)
