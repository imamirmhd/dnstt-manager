"""Resolver CRUD + metrics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import check_auth
from app.database import get_db
from app.models.resolver import Resolver
from app.models.metrics import ResolverMetricSnapshot
from app.schemas.resolver import (
    ResolverCreate,
    ResolverUpdate,
    ResolverResponse,
    ResolverBrief,
)
from app.schemas.system import ResolverMetricResponse

router = APIRouter(prefix="/api/resolvers", tags=["resolvers"], dependencies=[Depends(check_auth)])


@router.get("/", response_model=list[ResolverBrief])
async def list_resolvers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resolver).order_by(Resolver.id))
    resolvers = result.scalars().all()
    briefs = []
    for r in resolvers:
        brief = ResolverBrief.model_validate(r)
        # Count configurations using this resolver
        brief.config_count = len(r.configurations) if r.configurations else 0
        briefs.append(brief)
    return briefs


@router.post("/", response_model=ResolverResponse, status_code=status.HTTP_201_CREATED)
async def create_resolver(data: ResolverCreate, db: AsyncSession = Depends(get_db)):
    resolver = Resolver(**data.model_dump())
    db.add(resolver)
    await db.flush()
    await db.refresh(resolver)
    return ResolverResponse.model_validate(resolver)


@router.get("/{resolver_id}", response_model=ResolverResponse)
async def get_resolver(resolver_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resolver).where(Resolver.id == resolver_id))
    resolver = result.scalar_one_or_none()
    if resolver is None:
        raise HTTPException(status_code=404, detail="Resolver not found")
    return ResolverResponse.model_validate(resolver)


@router.put("/{resolver_id}", response_model=ResolverResponse)
async def update_resolver(resolver_id: int, data: ResolverUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resolver).where(Resolver.id == resolver_id))
    resolver = result.scalar_one_or_none()
    if resolver is None:
        raise HTTPException(status_code=404, detail="Resolver not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(resolver, key, value)

    await db.flush()
    await db.refresh(resolver)
    return ResolverResponse.model_validate(resolver)


@router.delete("/{resolver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resolver(resolver_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resolver).where(Resolver.id == resolver_id))
    resolver = result.scalar_one_or_none()
    if resolver is None:
        raise HTTPException(status_code=404, detail="Resolver not found")
    await db.delete(resolver)


@router.post("/{resolver_id}/test")
async def test_resolver(resolver_id: int):
    # Important: import here to avoid circular dependencies if needed,
    # or just use the global resolver_manager
    from app.core.resolver_manager import resolver_manager
    return await resolver_manager.test_single(resolver_id)


@router.get("/{resolver_id}/metrics", response_model=list[ResolverMetricResponse])
async def get_resolver_metrics(
    resolver_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ResolverMetricSnapshot)
        .where(ResolverMetricSnapshot.resolver_id == resolver_id)
        .order_by(ResolverMetricSnapshot.timestamp.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()
    return [ResolverMetricResponse.model_validate(s) for s in reversed(list(snapshots))]
