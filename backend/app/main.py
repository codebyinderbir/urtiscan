"""FastAPI application entry point: ``uvicorn app.main:app --reload``."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="UrtiScan API",
    version="0.1.0",
    description="Research prototype for AI-assisted wheal detection. Not a medical device.",
    lifespan=lifespan,
)
# The Vite dev server proxies /api, so CORS is only needed if the UI is served elsewhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
