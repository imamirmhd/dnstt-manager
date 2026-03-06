"""ORM model for DNS resolvers."""

from __future__ import annotations

import datetime

from sqlalchemy import String, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin


class Resolver(Base, IDMixin, TimestampMixin):
    __tablename__ = "resolvers"

    # Identity
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # Type: "doh" | "dot" | "udp"
    resolver_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # Address (URL for DoH, host:port for DoT/UDP)
    address: Mapped[str] = mapped_column(String(512), nullable=False)

    # Runtime state
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | testing | dead
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0–1.0
    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    failed_checks: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    configurations = relationship("Configuration", back_populates="resolver", lazy="selectin")
    metrics = relationship(
        "ResolverMetricSnapshot", back_populates="resolver",
        cascade="all, delete-orphan", lazy="selectin",
    )
