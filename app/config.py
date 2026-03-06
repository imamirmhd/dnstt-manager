"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


@dataclass
class Settings:
    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    # Auth (optional)
    username: str | None = None
    password: str | None = None
    # Database
    db_path: Path = field(default_factory=lambda: DATA_DIR / "dnstt_manager.db")
    # Core binary paths
    dnstt_client_path: str = "dnstt-client"
    slipstream_client_path: str = "slipstream-client"
    # Check intervals (seconds)
    health_check_interval: int = 60
    health_check_url: str = "http://gstatic.com/generate_204"
    health_check_samples: int = 3
    resolver_check_interval: int = 120
    system_monitor_interval: int = 5
    # Resolver dead threshold (hours)
    resolver_dead_threshold_hours: int = 24
    # Config dead threshold (hours)
    config_dead_threshold_hours: int = 24
    # Process restart
    max_restart_attempts: int = 5
    restart_backoff_base: float = 2.0  # exponential backoff base
    restart_window_seconds: int = 300  # window to count rapid restarts
    # HAProxy
    haproxy_config_path: Path = field(default_factory=lambda: DATA_DIR / "haproxy.cfg")
    haproxy_binary: str = "haproxy"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


# Singleton
settings = Settings()
