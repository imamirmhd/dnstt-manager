"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.core.process_manager import process_manager
from app.core.resolver_manager import resolver_manager
from app.core.health_checker import health_checker
from app.core.socks_layer import socks_layer_manager
from app.core.dns_balancer import dns_balancer_manager
from app.core.data_balancer import data_balancer_manager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Ensure data directory exists
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    # Init database
    await init_db()
    logger.info("Database initialized at %s", settings.db_path)

    # Load initial settings from DB to the active config
    from app.database import async_session
    from app.models.setting import Setting
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(Setting))
        for db_setting in result.scalars():
            if hasattr(settings, db_setting.key):
                curr = getattr(settings, db_setting.key)
                try:
                    if isinstance(curr, int):
                        setattr(settings, db_setting.key, int(db_setting.value))
                    elif isinstance(curr, float):
                        setattr(settings, db_setting.key, float(db_setting.value))
                    else:
                        setattr(settings, db_setting.key, str(db_setting.value))
                except ValueError:
                    logger.warning("Invalid value for setting %s: %s", db_setting.key, db_setting.value)
    logger.info("Loaded dynamic settings from database into active config")

    # Start background services
    await resolver_manager.start()
    await health_checker.start()
    
    # Start balancers (they check if they are enabled internally)
    await dns_balancer_manager.start()
    await data_balancer_manager.start()
    
    logger.info("Background services started")

    yield

    # Shutdown
    logger.info("Shutting down …")
    await health_checker.stop()
    await resolver_manager.stop()
    await dns_balancer_manager.stop()
    await data_balancer_manager.stop()
    await socks_layer_manager.stop_all()
    await process_manager.stop_all()
    logger.info("All services stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DNS Tunnel Manager",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Include routers ---
    from app.api.routes.configurations import router as config_router
    from app.api.routes.resolvers import router as resolver_router
    from app.api.routes.system import router as system_router
    from app.api.routes.balancer import router as balancer_router
    from app.api.routes.ws import router as ws_router

    app.include_router(config_router)
    app.include_router(resolver_router)
    app.include_router(system_router)
    app.include_router(balancer_router)
    app.include_router(ws_router)

    # --- Static files (SPA) ---
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
