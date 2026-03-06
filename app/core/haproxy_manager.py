"""HAProxy manager — generates config and manages the HAProxy process."""

from __future__ import annotations

import asyncio
import logging
import signal

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.configuration import Configuration
from app.models.setting import HAProxyConfig as HAProxyConfigModel

logger = logging.getLogger(__name__)

HAPROXY_TEMPLATE = """\
global
    daemon
    maxconn 4096
    log stdout format raw local0

defaults
    mode tcp
    timeout connect 5s
    timeout client  30s
    timeout server  30s
    log global
    option tcplog

frontend tunnel_frontend
    bind {listen_address}:{listen_port}
    default_backend tunnel_backends

backend tunnel_backends
    balance roundrobin
{servers}
{stats_section}
"""

STATS_SECTION = """\
frontend stats
    bind *:{stats_port}
    mode http
    stats enable
    stats uri /stats
    stats refresh 5s
"""


class HAProxyManager:
    """Generates HAProxy config and manages its lifecycle."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def pid(self) -> int | None:
        if self.is_running and self._process:
            return self._process.pid
        return None

    async def generate_config(self) -> str | None:
        """Generate HAProxy config from active healthy tunnels."""
        async with async_session() as session:
            # Load HAProxy settings
            result = await session.execute(select(HAProxyConfigModel))
            ha_config = result.scalar_one_or_none()
            if ha_config is None or not ha_config.enabled:
                return None

            # Get healthy, running configurations WITH a managed SOCKS port
            result = await session.execute(
                select(Configuration)
                .where(Configuration.status == "running")
                .where(Configuration.health == "healthy")
                .where(Configuration.socks_port.isnot(None))
            )
            configs = list(result.scalars().all())

        if not configs:
            logger.warning("No healthy configs with SOCKS proxy for HAProxy")
            return None

        # Build server lines — use managed SOCKS5 endpoints
        server_lines = []
        for cfg in configs:
            server_lines.append(
                f"    server {cfg.name} {cfg.socks_address}:{cfg.socks_port} check inter 10s"
            )

        stats = ""
        if ha_config.stats_enabled:
            stats = STATS_SECTION.format(stats_port=ha_config.stats_port)

        config_str = HAPROXY_TEMPLATE.format(
            listen_address=ha_config.listen_address,
            listen_port=ha_config.listen_port,
            servers="\n".join(server_lines),
            stats_section=stats,
        )

        # Write to file
        settings.haproxy_config_path.parent.mkdir(parents=True, exist_ok=True)
        settings.haproxy_config_path.write_text(config_str)
        logger.info("HAProxy config written to %s", settings.haproxy_config_path)
        return config_str

    async def start(self) -> dict:
        """Start or reload HAProxy."""
        config_str = await self.generate_config()
        if config_str is None:
            return {"ok": False, "message": "No config generated (disabled or no healthy backends)"}

        if self.is_running:
            return await self.reload()

        try:
            self._process = await asyncio.create_subprocess_exec(
                settings.haproxy_binary,
                "-f", str(settings.haproxy_config_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            logger.info("HAProxy started with PID %d", self._process.pid)
            return {"ok": True, "message": f"HAProxy started (PID {self._process.pid})"}
        except Exception as exc:
            logger.exception("Failed to start HAProxy: %s", exc)
            return {"ok": False, "message": str(exc)}

    async def stop(self) -> dict:
        if not self.is_running or self._process is None:
            return {"ok": False, "message": "Not running"}

        self._process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(self._process.wait(), timeout=10)
        except asyncio.TimeoutError:
            self._process.kill()

        self._process = None
        logger.info("HAProxy stopped")
        return {"ok": True, "message": "Stopped"}

    async def reload(self) -> dict:
        """Reload HAProxy config gracefully."""
        config_str = await self.generate_config()
        if config_str is None:
            return {"ok": False, "message": "Failed to generate config"}

        if self.is_running and self._process:
            self._process.send_signal(signal.SIGHUP)
            logger.info("HAProxy reloaded")
            return {"ok": True, "message": "Reloaded"}
        else:
            return await self.start()


# Module-level singleton
haproxy_manager = HAProxyManager()
