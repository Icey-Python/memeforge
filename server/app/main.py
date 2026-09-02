# memeforge
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.settings import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    OUTPUT_DIR,
)
from app.core.modules import init_routers, make_middleware


def create_app() -> FastAPI:
    app_ = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        middleware=make_middleware(),
    )
    init_routers(app_=app_)

    # Rendered videos + TTS previews land here and are served as statics.
    app_.mount(
        "/outputs",
        StaticFiles(directory=OUTPUT_DIR),
        name="outputs",
    )
    return app_


app = create_app()
