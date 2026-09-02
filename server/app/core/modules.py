"""App wiring: routers + middleware (template pattern)."""

import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.main_router import router

# Comma-separated list of extra allowed origins (production deployments).
_extra = os.getenv("MEMEFORGE_CORS_ORIGINS", "")
origins: List[str] = [o.strip() for o in _extra.split(",") if o.strip()]

# Local dev: any localhost port (Next dev/prod servers, preview tabs...).
allow_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


def init_routers(app_: FastAPI) -> None:
    app_.include_router(router)


def make_middleware() -> List[Middleware]:
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_origin_regex=allow_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]
