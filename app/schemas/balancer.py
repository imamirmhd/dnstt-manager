"""Pydantic schemas for DNS and Data balancer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ── DNS Balancer ──────────────────────────────────────────────

class DnsBalancerUpdate(BaseModel):
    enabled: bool | None = None
    listen_address: str | None = None
    udp_port: int | None = Field(default=None, ge=0, le=65535)
    dot_port: int | None = Field(default=None, ge=0, le=65535)
    doh_port: int | None = Field(default=None, ge=0, le=65535)
    strategy: str | None = Field(default=None, pattern=r"^(round_robin|least_latency|weighted)$")


class DnsBalancerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool
    listen_address: str
    udp_port: int
    dot_port: int
    doh_port: int
    strategy: str


class DnsBalancerStatus(BaseModel):
    running: bool
    udp_active: bool = False
    dot_active: bool = False
    doh_active: bool = False
    queries_handled: int = 0
    queries_failed: int = 0


# ── Data Balancer ─────────────────────────────────────────────

class DataBalancerUpdate(BaseModel):
    enabled: bool | None = None
    listen_address: str | None = None
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    strategy: str | None = Field(default=None, pattern=r"^(round_robin|least_connections|least_latency)$")


class DataBalancerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool
    listen_address: str
    listen_port: int
    strategy: str


class DataBalancerStatus(BaseModel):
    running: bool
    active_connections: int = 0
    total_connections: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    up_kbps: float = 0.0
    down_kbps: float = 0.0
    avg_ping_ms: float | None = None
    avg_latency_ms: float | None = None
    backends: list[dict] = []
    logs: list[str] = []
