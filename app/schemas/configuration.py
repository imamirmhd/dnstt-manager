"""Pydantic schemas for tunnel configurations."""

from __future__ import annotations

import datetime
from pydantic import BaseModel, ConfigDict, Field


class ConfigurationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    transport_type: str = Field(..., pattern=r"^(slipstream|dnstt)$")
    domain: str = Field(..., min_length=3, max_length=255)
    listen_address: str = Field(default="127.0.0.1")
    listen_port: int = Field(..., ge=1, le=65535)
    backend_type: str = Field(..., pattern=r"^(socks5|ssh)$")
    backend_host: str = Field(default="127.0.0.1")
    backend_port: int | None = Field(default=None, ge=1, le=65535)
    backend_user: str | None = None
    backend_password: str | None = None
    pubkey: str | None = None
    cert_path: str | None = None
    socks_address: str = Field(default="127.0.0.1")
    socks_port: int | None = Field(default=None, ge=1, le=65535)
    resolver_mode: str = Field(default="smart", pattern=r"^(smart|manual)$")
    resolver_id: int | None = None
    extra: str | None = None


class ConfigurationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    transport_type: str | None = Field(default=None, pattern=r"^(slipstream|dnstt)$")
    domain: str | None = Field(default=None, min_length=3, max_length=255)
    listen_address: str | None = None
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    backend_type: str | None = Field(default=None, pattern=r"^(socks5|ssh)$")
    backend_host: str | None = None
    backend_port: int | None = Field(default=None, ge=1, le=65535)
    backend_user: str | None = None
    backend_password: str | None = None
    pubkey: str | None = None
    cert_path: str | None = None
    socks_address: str | None = None
    socks_port: int | None = Field(default=None, ge=1, le=65535)
    resolver_mode: str | None = Field(default=None, pattern=r"^(smart|manual)$")
    resolver_id: int | None = None
    extra: str | None = None


class ConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    transport_type: str
    domain: str
    listen_address: str
    listen_port: int
    backend_type: str
    backend_host: str
    backend_port: int | None
    backend_user: str | None
    backend_password: str | None
    pubkey: str | None
    cert_path: str | None
    socks_address: str
    socks_port: int | None
    resolver_mode: str
    resolver_id: int | None
    status: str
    health: str
    pid: int | None
    socks_pid: int | None
    restart_count: int
    extra: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ConfigurationBrief(BaseModel):
    """Lightweight representation for dashboard cards."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    transport_type: str
    domain: str
    listen_address: str
    listen_port: int
    backend_type: str
    socks_address: str
    socks_port: int | None
    status: str
    health: str
    resolver_id: int | None = None
    resolver_name: str | None = None
