"""ORM models for time-series metric snapshots."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin


class ConfigMetricSnapshot(Base, IDMixin):
    """Periodic metric snapshot for a tunnel configuration."""
    __tablename__ = "config_metric_snapshots"

    configuration_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("configurations.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    http_ping_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    download_speed_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    upload_speed_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_alive: Mapped[bool] = mapped_column(default=True)

    # Relationship
    configuration = relationship("Configuration", back_populates="metrics")


class ResolverMetricSnapshot(Base, IDMixin):
    """Periodic metric snapshot for a resolver."""
    __tablename__ = "resolver_metric_snapshots"

    resolver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resolvers.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    dns_query_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationship
    resolver = relationship("Resolver", back_populates="metrics")
