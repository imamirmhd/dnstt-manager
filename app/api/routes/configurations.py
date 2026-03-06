"""Configuration CRUD + control routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import check_auth
from app.database import get_db
from app.models.configuration import Configuration
from app.models.metrics import ConfigMetricSnapshot
from app.schemas.configuration import (
    ConfigurationCreate,
    ConfigurationUpdate,
    ConfigurationResponse,
    ConfigurationBrief,
)
from app.schemas.system import ConfigMetricResponse
from app.core.process_manager import process_manager
from app.core.socks_layer import socks_layer_manager

router = APIRouter(prefix="/api/configurations", tags=["configurations"], dependencies=[Depends(check_auth)])


@router.get("/", response_model=list[ConfigurationBrief])
async def list_configurations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).order_by(Configuration.id))
    configs = result.scalars().all()
    
    # Batch fetch the latest metric for each config to avoid N+1 queries
    config_ids = [c.id for c in configs]
    metrics_map = {}
    if config_ids:
        # Get the row with the max timestamp per configuration
        from sqlalchemy import func
        subq = (
            select(
                ConfigMetricSnapshot.configuration_id,
                func.max(ConfigMetricSnapshot.timestamp).label("max_ts")
            )
            .where(ConfigMetricSnapshot.configuration_id.in_(config_ids))
            .group_by(ConfigMetricSnapshot.configuration_id)
            .subquery()
        )
        
        latest_metrics_query = (
            select(ConfigMetricSnapshot)
            .join(
                subq,
                (ConfigMetricSnapshot.configuration_id == subq.c.configuration_id) &
                (ConfigMetricSnapshot.timestamp == subq.c.max_ts)
            )
        )
        m_res = await db.execute(latest_metrics_query)
        for m in m_res.scalars().all():
            metrics_map[m.configuration_id] = m

    briefs = []
    for c in configs:
        brief = ConfigurationBrief.model_validate(c)
        if c.resolver:
            brief.resolver_name = c.resolver.name
            
        latest_metric = metrics_map.get(c.id)
        if latest_metric:
            brief.last_ping_ms = latest_metric.http_ping_ms
            brief.last_latency_ms = latest_metric.latency_ms
            
        briefs.append(brief)
    return briefs


@router.post("/", response_model=ConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_configuration(data: ConfigurationCreate, db: AsyncSession = Depends(get_db)):
    cfg = Configuration(**data.model_dump())
    db.add(cfg)
    await db.flush()
    await db.refresh(cfg)
    return ConfigurationResponse.model_validate(cfg)


@router.get("/{config_id}", response_model=ConfigurationResponse)
async def get_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return ConfigurationResponse.model_validate(cfg)


@router.put("/{config_id}", response_model=ConfigurationResponse)
async def update_configuration(config_id: int, data: ConfigurationUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Configuration not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(cfg, key, value)

    await db.flush()
    await db.refresh(cfg)
    return ConfigurationResponse.model_validate(cfg)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    # Stop if running
    await process_manager.stop(config_id)

    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    await db.delete(cfg)


# --- Control actions ---

@router.post("/{config_id}/start")
async def start_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return await process_manager.start(config_id)


@router.post("/{config_id}/stop")
async def stop_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return await process_manager.stop(config_id)


@router.post("/{config_id}/restart")
async def restart_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return await process_manager.restart(config_id)


@router.post("/{config_id}/test")
async def test_configuration(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.id == config_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
        
    from app.core.health_checker import health_checker
    res = await health_checker._check_config(cfg)
    return res


@router.post("/test-all")
async def test_all_configurations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.status == "running"))
    configs = list(result.scalars().all())
    
    from app.core.health_checker import health_checker
    
    # We will just trigger a background task to check everyone and save to DB
    # We don't want to block the HTTP response if there are 100+ tunnels
    import asyncio
    asyncio.create_task(health_checker._run_checks())
    
    return {"ok": True, "message": f"Testing {len(configs)} running configurations in the background."}


@router.post("/restart-all")
async def restart_all_configurations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.status == "running"))
    configs = list(result.scalars().all())
    
    import asyncio
    
    async def _restart_bg():
        for c in configs:
            await process_manager.restart(c.id)
            await asyncio.sleep(0.5)  # stagger slightly
            
    asyncio.create_task(_restart_bg())
    
    return {"ok": True, "message": f"Restarting {len(configs)} configurations in the background."}


@router.post("/start-all")
async def start_all_configurations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.status != "running"))
    configs = list(result.scalars().all())
    
    import asyncio
    
    async def _start_bg():
        for c in configs:
            await process_manager.start(c.id)
            await asyncio.sleep(0.5)
            
    asyncio.create_task(_start_bg())
    
    return {"ok": True, "message": f"Starting {len(configs)} configurations in the background."}


@router.post("/stop-all")
async def stop_all_configurations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Configuration).where(Configuration.status == "running"))
    configs = list(result.scalars().all())
    
    import asyncio
    
    async def _stop_bg():
        for c in configs:
            await process_manager.stop(c.id)
            await asyncio.sleep(0.1)
            
    asyncio.create_task(_stop_bg())
    
    return {"ok": True, "message": f"Stopping {len(configs)} configurations in the background."}


@router.get("/{config_id}/logs")
async def get_configuration_logs(config_id: int):
    logs = process_manager.get_logs(config_id)
    return {"config_id": config_id, "logs": logs}


@router.delete("/{config_id}/logs")
async def delete_configuration_logs(config_id: int):
    """Delete all logs for a configuration."""
    process_manager.clear_logs(config_id)
    return {"ok": True, "message": "Logs cleared"}


@router.get("/{config_id}/metrics", response_model=list[ConfigMetricResponse])
async def get_configuration_metrics(
    config_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ConfigMetricSnapshot)
        .where(ConfigMetricSnapshot.configuration_id == config_id)
        .order_by(ConfigMetricSnapshot.timestamp.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()
    return [ConfigMetricResponse.model_validate(s) for s in reversed(list(snapshots))]


@router.get("/{config_id}/bandwidth")
async def get_configuration_bandwidth(config_id: int):
    bw = socks_layer_manager.get_bandwidth(config_id)
    if bw is None:
        return {"config_id": config_id, "active": False}
    return {"config_id": config_id, "active": True, **bw}
