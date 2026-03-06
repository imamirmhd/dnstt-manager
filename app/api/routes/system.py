"""System stats, settings, HAProxy control routes."""

from __future__ import annotations

import socket

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import check_auth
from app.database import get_db
from app.models.configuration import Configuration
from app.models.resolver import Resolver
from app.models.setting import Setting, HAProxyConfig as HAProxyConfigModel
from app.schemas.system import (
    DashboardOverview,
    HAProxyConfigResponse,
    HAProxyConfigUpdate,
    HAProxyStatus,
    SettingResponse,
    SettingUpdate,
    SystemStats,
)
from app.core.system_monitor import system_monitor
from app.core.haproxy_manager import haproxy_manager

router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(check_auth)])


# --- Dashboard ---

@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    stats = await system_monitor.async_snapshot()

    # Count configs
    result = await db.execute(select(Configuration))
    configs = list(result.scalars().all())
    total_configs = len(configs)
    running_configs = sum(1 for c in configs if c.status == "running")
    healthy_configs = sum(1 for c in configs if c.health == "healthy")

    # Count resolvers
    result = await db.execute(select(Resolver))
    resolvers = list(result.scalars().all())
    total_resolvers = len(resolvers)
    active_resolvers = sum(1 for r in resolvers if r.status == "active")
    dead_resolvers = sum(1 for r in resolvers if r.status == "dead")

    return DashboardOverview(
        system=stats,
        total_configurations=total_configs,
        running_configurations=running_configs,
        healthy_configurations=healthy_configs,
        total_resolvers=total_resolvers,
        active_resolvers=active_resolvers,
        dead_resolvers=dead_resolvers,
        haproxy_running=haproxy_manager.is_running,
    )


@router.get("/stats", response_model=SystemStats)
async def get_system_stats():
    return await system_monitor.async_snapshot()


# --- Settings ---

@router.get("/settings", response_model=list[SettingResponse])
async def list_settings():
    from app.config import settings as app_settings
    
    keys = [
        "dnstt_client_path",
        "slipstream_client_path",
        "haproxy_binary",
        "health_check_interval",
        "health_check_url",
        "health_check_samples",
        "resolver_check_interval",
        "system_monitor_interval",
        "resolver_dead_threshold_hours",
        "max_restart_attempts",
        "restart_backoff_base",
        "restart_window_seconds",
    ]
    
    responses = []
    for k in keys:
        if hasattr(app_settings, k):
            responses.append(SettingResponse(key=k, value=str(getattr(app_settings, k))))
            
    return responses


@router.put("/settings")
async def update_setting(data: SettingUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting).where(Setting.key == data.key))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(key=data.key, value=data.value)
        db.add(setting)
    else:
        setting.value = data.value
    await db.flush()
    await db.refresh(setting)

    # Update active config instance dynamically
    from app.config import settings as app_settings
    if hasattr(app_settings, data.key):
        curr = getattr(app_settings, data.key)
        try:
            if isinstance(curr, int):
                setattr(app_settings, data.key, int(data.value))
            elif isinstance(curr, float):
                setattr(app_settings, data.key, float(data.value))
            else:
                setattr(app_settings, data.key, str(data.value))
        except ValueError:
            pass

    return SettingResponse.model_validate(setting)


# --- HAProxy ---

@router.get("/haproxy", response_model=HAProxyStatus)
async def get_haproxy_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HAProxyConfigModel))
    ha_config = result.scalar_one_or_none()

    config_resp = None
    if ha_config:
        config_resp = HAProxyConfigResponse.model_validate(ha_config)

    # Count active backends
    result2 = await db.execute(
        select(Configuration)
        .where(Configuration.status == "running")
        .where(Configuration.health == "healthy")
    )
    active_backends = len(list(result2.scalars().all()))

    return HAProxyStatus(
        running=haproxy_manager.is_running,
        pid=haproxy_manager.pid,
        config=config_resp,
        active_backends=active_backends,
    )


@router.put("/haproxy")
async def update_haproxy_config(data: HAProxyConfigUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HAProxyConfigModel))
    ha_config = result.scalar_one_or_none()
    if ha_config is None:
        ha_config = HAProxyConfigModel()
        db.add(ha_config)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ha_config, key, value)

    await db.flush()
    await db.refresh(ha_config)

    # If we just enabled/disabled, start/stop accordingly
    if data.enabled is True:
        result = await haproxy_manager.start()
        return {"config": HAProxyConfigResponse.model_validate(ha_config), **result}
    elif data.enabled is False:
        result = await haproxy_manager.stop()
        return {"config": HAProxyConfigResponse.model_validate(ha_config), **result}

    return {"config": HAProxyConfigResponse.model_validate(ha_config), "ok": True}


@router.post("/haproxy/reload")
async def reload_haproxy():
    return await haproxy_manager.reload()


# --- Utility ---

@router.get("/free-port")
async def get_free_port():
    """Find an available port on the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    return {"port": port}
