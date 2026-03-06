"""Pydantic schemas for DNS resolvers."""

from __future__ import annotations

import datetime
from pydantic import BaseModel, ConfigDict, Field


class ResolverCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    resolver_type: str = Field(..., pattern=r"^(doh|dot|udp)$")
    address: str = Field(..., min_length=3, max_length=512)


class ResolverUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    resolver_type: str | None = Field(default=None, pattern=r"^(doh|dot|udp)$")
    address: str | None = Field(default=None, min_length=3, max_length=512)


class ResolverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    resolver_type: str
    address: str
    status: str
    last_success_at: datetime.datetime | None
    last_latency_ms: float | None
    success_rate: float
    total_checks: int
    failed_checks: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ResolverBrief(BaseModel):
    """Lightweight representation for dashboard cards."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    resolver_type: str
    address: str
    status: str
    last_latency_ms: float | None
    success_rate: float
    total_checks: int = 0
    config_count: int = 0
