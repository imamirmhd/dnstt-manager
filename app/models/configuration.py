"""ORM model for tunnel configurations."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin


class Configuration(Base, IDMixin, TimestampMixin):
    __tablename__ = "configurations"

    # Identity
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # Transport: "slipstream" | "dnstt"
    transport_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # DNS domain for the tunnel (e.g. t.example.com)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)

    # Local listen endpoint — clients connect here
    listen_address: Mapped[str] = mapped_column(String(64), default="127.0.0.1")
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False)

    # Backend type: "socks5" | "ssh"
    backend_type: Mapped[str] = mapped_column(String(32), nullable=False)
    backend_host: Mapped[str] = mapped_column(String(255), default="127.0.0.1")
    backend_port: Mapped[int] = mapped_column(Integer, nullable=True)
    backend_user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    backend_password: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Transport-specific: public key (dnstt) or cert path (slipstream)
    pubkey: Mapped[str | None] = mapped_column(Text, nullable=True)
    cert_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Resolver selection
    resolver_mode: Mapped[str] = mapped_column(String(16), default="smart")  # "smart" | "manual"
    resolver_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resolvers.id", ondelete="SET NULL"), nullable=True
    )

    # Managed SOCKS5 proxy layer (uniform endpoint for HAProxy)
    socks_address: Mapped[str] = mapped_column(String(64), default="127.0.0.1")
    socks_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Runtime state
    status: Mapped[str] = mapped_column(String(32), default="stopped")  # stopped | running | starting | error
    health: Mapped[str] = mapped_column(String(32), default="unknown")  # healthy | unhealthy | unknown
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socks_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restart_count: Mapped[int] = mapped_column(Integer, default=0)

    # Extra notes / raw JSON config
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    resolver = relationship("Resolver", back_populates="configurations", lazy="selectin")
    metrics = relationship(
        "ConfigMetricSnapshot", back_populates="configuration",
        cascade="all, delete-orphan", lazy="selectin",
    )
