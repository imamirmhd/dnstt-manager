"""ORM models for DNS and Data balancer configurations."""

from __future__ import annotations

from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IDMixin, TimestampMixin


class DnsBalancerConfig(Base, IDMixin, TimestampMixin):
    """DNS Balancer settings — local DNS proxy forwarding to the best resolver."""
    __tablename__ = "dns_balancer_config"

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    listen_address: Mapped[str] = mapped_column(String(64), default="0.0.0.0")
    udp_port: Mapped[int] = mapped_column(Integer, default=5353)
    dot_port: Mapped[int] = mapped_column(Integer, default=8853)
    doh_port: Mapped[int] = mapped_column(Integer, default=8443)
    # Strategy: round_robin | least_latency | weighted
    strategy: Mapped[str] = mapped_column(String(32), default="least_latency")


class DataBalancerConfig(Base, IDMixin, TimestampMixin):
    """Data Balancer settings — TCP load balancer across config SOCKS endpoints."""
    __tablename__ = "data_balancer_config"

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    listen_address: Mapped[str] = mapped_column(String(64), default="0.0.0.0")
    listen_port: Mapped[int] = mapped_column(Integer, default=1080)
    # Strategy: round_robin | least_connections | least_latency
    strategy: Mapped[str] = mapped_column(String(32), default="round_robin")
