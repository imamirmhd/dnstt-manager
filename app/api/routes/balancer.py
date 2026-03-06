"""Balancer API routes — DNS Balancer + Data Balancer."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import check_auth
from app.database import get_db
from app.models.balancer import DnsBalancerConfig, DataBalancerConfig
from app.schemas.balancer import (
    DnsBalancerUpdate,
    DnsBalancerResponse,
    DnsBalancerStatus,
    DataBalancerUpdate,
    DataBalancerResponse,
    DataBalancerStatus,
)
from app.core.dns_balancer import dns_balancer_manager
from app.core.data_balancer import data_balancer_manager

router = APIRouter(prefix="/api/balancer", tags=["balancer"], dependencies=[Depends(check_auth)])


# ── DNS Balancer ──────────────────────────────────────────────

@router.get("/dns", response_model=DnsBalancerResponse)
async def get_dns_balancer_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DnsBalancerConfig))
    config = result.scalar_one_or_none()
    if config is None:
        # Auto-create default config
        config = DnsBalancerConfig()
        db.add(config)
        await db.flush()
        await db.refresh(config)
    return DnsBalancerResponse.model_validate(config)


@router.put("/dns", response_model=DnsBalancerResponse)
async def update_dns_balancer_config(data: DnsBalancerUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DnsBalancerConfig))
    config = result.scalar_one_or_none()
    if config is None:
        config = DnsBalancerConfig()
        db.add(config)
        await db.flush()
        await db.refresh(config)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.flush()
    await db.refresh(config)
    return DnsBalancerResponse.model_validate(config)


@router.post("/dns/start")
async def start_dns_balancer():
    return await dns_balancer_manager.start()


@router.post("/dns/stop")
async def stop_dns_balancer():
    return await dns_balancer_manager.stop()


@router.get("/dns/status", response_model=DnsBalancerStatus)
async def dns_balancer_status():
    return dns_balancer_manager.get_status()


# ── Data Balancer ─────────────────────────────────────────────

@router.get("/data", response_model=DataBalancerResponse)
async def get_data_balancer_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataBalancerConfig))
    config = result.scalar_one_or_none()
    if config is None:
        config = DataBalancerConfig()
        db.add(config)
        await db.flush()
        await db.refresh(config)
    return DataBalancerResponse.model_validate(config)


@router.put("/data", response_model=DataBalancerResponse)
async def update_data_balancer_config(data: DataBalancerUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataBalancerConfig))
    config = result.scalar_one_or_none()
    if config is None:
        config = DataBalancerConfig()
        db.add(config)
        await db.flush()
        await db.refresh(config)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.flush()
    await db.refresh(config)
    return DataBalancerResponse.model_validate(config)


@router.post("/data/start")
async def start_data_balancer():
    return await data_balancer_manager.start()


@router.post("/data/stop")
async def stop_data_balancer():
    return await data_balancer_manager.stop()


@router.get("/data/status", response_model=DataBalancerStatus)
async def data_balancer_status():
    return data_balancer_manager.get_status()
