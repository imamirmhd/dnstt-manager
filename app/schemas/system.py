"""Pydantic schemas for system stats, settings, and HAProxy."""

from __future__ import annotations

import datetime
from pydantic import BaseModel, ConfigDict, Field


# --- System stats ---

class SystemStats(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    net_sent_bytes: int
    net_recv_bytes: int
    net_sent_rate_kbps: float = 0.0
    net_recv_rate_kbps: float = 0.0
    uptime_seconds: float = 0.0
    load_avg_1: float = 0.0
    load_avg_5: float = 0.0
    load_avg_15: float = 0.0


# --- Settings ---

class SettingUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str | None = None


class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


# --- HAProxy ---

class HAProxyConfigUpdate(BaseModel):
    enabled: bool | None = None
    listen_address: str | None = None
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    stats_enabled: bool | None = None
    stats_port: int | None = Field(default=None, ge=1, le=65535)


class HAProxyConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool
    listen_address: str
    listen_port: int
    stats_enabled: bool
    stats_port: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class HAProxyStatus(BaseModel):
    running: bool = False
    pid: int | None = None
    config: HAProxyConfigResponse | None = None
    active_backends: int = 0


# --- Metric snapshots for API ---

class ConfigMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    configuration_id: int
    timestamp: datetime.datetime
    latency_ms: float | None
    http_ping_ms: float | None
    download_speed_kbps: float | None
    upload_speed_kbps: float | None
    is_alive: bool


class ResolverMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resolver_id: int
    timestamp: datetime.datetime
    latency_ms: float | None
    success: bool
    dns_query_time_ms: float | None


# --- Dashboard overview ---

class DashboardOverview(BaseModel):
    system: SystemStats
    total_configurations: int = 0
    running_configurations: int = 0
    healthy_configurations: int = 0
    total_resolvers: int = 0
    active_resolvers: int = 0
    dead_resolvers: int = 0
    haproxy_running: bool = False
