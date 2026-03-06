"""Health checker — periodic config health metrics (latency, speed, HTTP ping)."""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.configuration import Configuration
from app.models.metrics import ConfigMetricSnapshot

logger = logging.getLogger(__name__)


class HealthChecker:
    """Periodically probes running tunnel configs via their SOCKS proxy endpoint."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("HealthChecker started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HealthChecker stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_checks()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Health check error: %s", exc)
            await asyncio.sleep(settings.health_check_interval)

    async def _run_checks(self) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Configuration).where(Configuration.status == "running")
            )
            configs = list(result.scalars().all())

        if not configs:
            return

        # Set health to "checking" for all running configs
        async with async_session() as session:
            for cfg in configs:
                res = await session.execute(
                    select(Configuration).where(Configuration.id == cfg.id)
                )
                c = res.scalar_one_or_none()
                if c and c.status == "running":
                    c.health = "checking"
            await session.commit()

        results = await asyncio.gather(
            *[self._check_config(c) for c in configs],
            return_exceptions=True,
        )

        # Get bandwidth data from socks_layer for speed metrics
        from app.core.socks_layer import socks_layer_manager
        bandwidth_data = {}
        for cfg in configs:
            try:
                bw = socks_layer_manager.get_bandwidth(cfg.id)
                if bw and bw.get("active"):
                    bandwidth_data[cfg.id] = bw
            except Exception:
                pass

        async with async_session() as session:
            for cfg, check in zip(configs, results):
                bw = bandwidth_data.get(cfg.id, {})

                if isinstance(check, Exception):
                    snapshot = ConfigMetricSnapshot(
                        configuration_id=cfg.id,
                        is_alive=False,
                        download_speed_kbps=bw.get("down_kbps"),
                        upload_speed_kbps=bw.get("up_kbps"),
                    )
                    session.add(snapshot)
                    res = await session.execute(
                        select(Configuration).where(Configuration.id == cfg.id)
                    )
                    c = res.scalar_one_or_none()
                    if c:
                        c.health = "unhealthy"
                else:
                    snapshot = ConfigMetricSnapshot(
                        configuration_id=cfg.id,
                        latency_ms=check.get("latency_ms"),
                        http_ping_ms=check.get("http_ping_ms"),
                        download_speed_kbps=bw.get("down_kbps", check.get("download_speed_kbps")),
                        upload_speed_kbps=bw.get("up_kbps", check.get("upload_speed_kbps")),
                        is_alive=check.get("is_alive", True),
                    )
                    session.add(snapshot)

                    res = await session.execute(
                        select(Configuration).where(Configuration.id == cfg.id)
                    )
                    c = res.scalar_one_or_none()
                    if c and check.get("is_alive"):
                        c.health = "healthy"

            await session.commit()

    async def _check_config(self, cfg: Configuration) -> dict:
        """Probe a tunnel config with a two-phase check.

        Phase 1: TCP connectivity test to the tunnel listen port.
        Phase 2: If SOCKS proxy is available, test through it.
        """
        result: dict = {"is_alive": False}

        # ----- Phase 1: TCP connectivity to the tunnel listen port -----
        try:
            start = time.monotonic()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(cfg.listen_address, cfg.listen_port),
                timeout=10,
            )
            elapsed = (time.monotonic() - start) * 1000
            writer.close()
            await writer.wait_closed()
            result["is_alive"] = True
            result["latency_ms"] = elapsed
        except Exception as exc:
            logger.debug("TCP check for %s (:%d) failed: %s", cfg.name, cfg.listen_port, exc)
            return result  # Tunnel is down, no point testing SOCKS

        # ----- Phase 2: SOCKS5 proxy test (if available) -----
        socks_host = cfg.socks_address or "127.0.0.1"
        socks_port = cfg.socks_port

        if socks_port and cfg.backend_type == "socks5":
            # Test SOCKS5 by doing a SOCKS5 handshake (no-auth greeting)
            try:
                start = time.monotonic()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(socks_host, socks_port),
                    timeout=10,
                )
                # SOCKS5 greeting: version=5, 1 auth method, no-auth=0
                writer.write(b'\x05\x01\x00')
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(2), timeout=5)
                writer.close()
                await writer.wait_closed()

                elapsed = (time.monotonic() - start) * 1000
                if len(resp) >= 2 and resp[0] == 0x05:
                    result["http_ping_ms"] = elapsed
                else:
                    logger.debug("SOCKS5 handshake failed for %s: %r", cfg.name, resp)
            except Exception as exc:
                logger.debug("SOCKS5 check for %s (:%d) failed: %s", cfg.name, socks_port, exc)

        return result


# Module-level singleton
health_checker = HealthChecker()
