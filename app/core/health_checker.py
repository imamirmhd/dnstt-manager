"""Health checker — periodic config health metrics (latency, speed, HTTP ping)."""

from __future__ import annotations

import asyncio
import logging
import time

import struct
import urllib.parse
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

        if socks_port and cfg.backend_type in ("socks5", "ssh"):
            samples = settings.health_check_samples
            url = settings.health_check_url
            successes = 0
            total_ping = 0.0

            for _ in range(samples):
                ping = await self._socks5_http_ping(socks_host, socks_port, url, timeout=10)
                if ping is not None:
                    successes += 1
                    total_ping += ping

            # A configuration must have at least one successful sample to be considered alive at the HTTP level
            if successes > 0:
                result["http_ping_ms"] = total_ping / successes
                result["is_alive"] = True
            else:
                result["http_ping_ms"] = None
                result["is_alive"] = False

        return result

    async def _socks5_http_ping(self, socks_host: str, socks_port: int, target_url: str, timeout: int = 10) -> float | None:
        """Perform a pure-Python SOCKS5 handshake and HTTP GET to measure true latency."""
        try:
            parsed = urllib.parse.urlparse(target_url)
            target_host = parsed.hostname
            target_port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            target_path = parsed.path or '/'
            if parsed.query:
                target_path += '?' + parsed.query
                
            start = time.monotonic()
            
            # 1. Connect to SOCKS5 proxy
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(socks_host, socks_port),
                timeout=timeout
            )
            
            # 2. SOCKS5 Greeting
            writer.write(b'\x05\x01\x00')
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(2), timeout=timeout)
            if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
                writer.close()
                return None
                
            # 3. SOCKS5 Connect Request (Domain Name)
            host_bytes = target_host.encode('utf-8')
            req = struct.pack(f"!BBBBB{len(host_bytes)}sH", 5, 1, 0, 3, len(host_bytes), host_bytes, target_port)
            writer.write(req)
            await writer.drain()
            
            # 4. SOCKS5 Connect Response
            resp = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
            if resp[0] != 0x05 or resp[1] != 0x00:
                writer.close()
                return None
                
            atyp = resp[3]
            if atyp == 0x01: # IPv4
                await asyncio.wait_for(reader.readexactly(4 + 2), timeout=timeout)
            elif atyp == 0x03: # Domain name
                domain_len = (await asyncio.wait_for(reader.readexactly(1), timeout=timeout))[0]
                await asyncio.wait_for(reader.readexactly(domain_len + 2), timeout=timeout)
            elif atyp == 0x04: # IPv6
                await asyncio.wait_for(reader.readexactly(16 + 2), timeout=timeout)
            
            # If HTTPS, we wrap in TLS
            if parsed.scheme == 'https':
                import ssl
                ssl_ctx = ssl.create_default_context()
                # Not doing hostname check to keep it simple/fast
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                
                transport = writer.transport
                protocol = transport.get_protocol()
                loop = asyncio.get_event_loop()
                
                # We need to manually do the TLS handshake
                tls_transport = await loop.start_tls(transport, protocol, ssl_ctx, server_hostname=target_host)
                
                # Replace the original writer's transport with the TLS one so writes work
                writer._transport = tls_transport
                # reader receives data from the protocol via feed_data, which the tls_transport handles
            
            # 5. Send HTTP GET
            http_req = f"GET {target_path} HTTP/1.1\r\nHost: {target_host}\r\nConnection: close\r\n\r\n"
            writer.write(http_req.encode('utf-8'))
            await writer.drain()
            
            # 6. Read HTTP Response
            resp_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            
            elapsed = (time.monotonic() - start) * 1000
            
            writer.close()
            await writer.wait_closed()
            
            if not resp_line.startswith(b"HTTP/"):
                return None
            return elapsed
            
        except Exception as exc:
            logger.debug("SOCKS5 HTTP ping failed for %s:%d -> %s: %s", socks_host, socks_port, target_url, exc)
            return None


# Module-level singleton
health_checker = HealthChecker()
