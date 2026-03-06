"""ORM models for application settings."""

from __future__ import annotations

from sqlalchemy import String, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IDMixin, TimestampMixin


class Setting(Base, IDMixin, TimestampMixin):
    """Generic key-value settings store."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


class HAProxyConfig(Base, IDMixin, TimestampMixin):
    """HAProxy intelligent mode configuration."""
    __tablename__ = "haproxy_config"

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    listen_address: Mapped[str] = mapped_column(String(64), default="0.0.0.0")
    listen_port: Mapped[int] = mapped_column(Integer, default=1080)
    stats_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    stats_port: Mapped[int] = mapped_column(Integer, default=8404)
