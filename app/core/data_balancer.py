"""Data Balancer — TCP load balancer distributing traffic across config SOCKS endpoints.

Accepts connections on a configured address:port and forwards them to the best
healthy running configuration's SOCKS endpoint based on the configured strategy.
Tracks per-backend bandwidth, latency, and ping metrics.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import random
import time

from sqlalchemy import select

from app.database import async_session
from app.models.configuration import Configuration
from app.models.balancer import DataBalancerConfig

logger = logging.getLogger(__name__)

LOG_BUFFER_MAX = 200


class _BackendStats:
    """Per-backend connection tracking with bandwidth and latency."""

    def __init__(self, config_id: int, address: str, port: int, latency_ms: float | None = None):
        self.config_id = config_id
        self.address = address
        self.port = port
        self.active_connections = 0
        self.total_connections = 0
        self.latency_ms = latency_ms
        self.ping_ms: float | None = None
        self.bytes_up = 0
        self.bytes_down = 0
        self.errors = 0


class DataBalancerManager:
    """Manages a TCP load balancer across tunnel SOCKS endpoints."""

    def __init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._running = False
        self._rr_index = 0
        self._backends: dict[int, _BackendStats] = {}
        self.total_connections = 0
        self.active_connections = 0
        self.bytes_up = 0
        self.bytes_down = 0
        self._logs: collections.deque = collections.deque(maxlen=LOG_BUFFER_MAX)
        self._prev_bytes_up = 0
        self._prev_bytes_down = 0
        self._prev_speed_ts = time.monotonic()
        self._up_kbps = 0.0
        self._down_kbps = 0.0
        self._speed_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> dict:
        if self._running:
            return {"ok": False, "message": "Already running"}

        config = await self._load_config()
        if config is None:
            return {"ok": False, "message": "No Data balancer config found"}

        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                host=config.listen_address,
                port=config.listen_port,
            )
            self._running = True
            self._log(f"Data Balancer listening on {config.listen_address}:{config.listen_port}")
            logger.info(
                "Data Balancer listening on %s:%d",
                config.listen_address, config.listen_port,
            )

            # Start background speed calculator and ping checker
            self._speed_task = asyncio.create_task(self._speed_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())

            return {
                "ok": True,
                "message": f"Data Balancer on {config.listen_address}:{config.listen_port}",
            }
        except Exception as exc:
            logger.exception("Failed to start Data Balancer: %s", exc)
            return {"ok": False, "message": str(exc)}

    async def stop(self) -> dict:
        if not self._running:
            return {"ok": False, "message": "Not running"}

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._speed_task and not self._speed_task.done():
            self._speed_task.cancel()
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()

        self._running = False
        self._backends.clear()
        self._log("Data Balancer stopped")
        logger.info("Data Balancer stopped")
        return {"ok": True, "message": "Stopped"}

    def get_status(self) -> dict:
        # Calculate average ping/latency across backends
        pings = [b.ping_ms for b in self._backends.values() if b.ping_ms is not None]
        latencies = [b.latency_ms for b in self._backends.values() if b.latency_ms is not None]
        avg_ping = sum(pings) / len(pings) if pings else None
        avg_latency = sum(latencies) / len(latencies) if latencies else None

        return {
            "running": self._running,
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "bytes_up": self.bytes_up,
            "bytes_down": self.bytes_down,
            "up_kbps": round(self._up_kbps, 1),
            "down_kbps": round(self._down_kbps, 1),
            "avg_ping_ms": round(avg_ping, 1) if avg_ping is not None else None,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
            "backends": [
                {
                    "config_id": b.config_id,
                    "address": f"{b.address}:{b.port}",
                    "active": b.active_connections,
                    "total": b.total_connections,
                    "bytes_up": b.bytes_up,
                    "bytes_down": b.bytes_down,
                    "latency_ms": b.latency_ms,
                    "ping_ms": b.ping_ms,
                    "errors": b.errors,
                }
                for b in self._backends.values()
            ],
            "logs": list(self._logs),
        }

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Accept client connection and proxy to a selected backend."""
        backend = await self._select_backend()
        if backend is None:
            logger.debug("Data Balancer: no healthy backends")
            self._log("Connection rejected: no healthy backends")
            writer.close()
            return

        self.total_connections += 1
        self.active_connections += 1
        backend.active_connections += 1
        backend.total_connections += 1

        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"
        self._log(f"Connection from {peer_str} → {backend.address}:{backend.port} (config #{backend.config_id})")

        try:
            start = time.monotonic()
            up_reader, up_writer = await asyncio.wait_for(
                asyncio.open_connection(backend.address, backend.port),
                timeout=10,
            )
            connect_time = (time.monotonic() - start) * 1000
            backend.latency_ms = connect_time
        except Exception as exc:
            logger.debug("Data Balancer: backend connect failed: %s", exc)
            self._log(f"Backend connect failed: {backend.address}:{backend.port} — {exc}")
            self.active_connections -= 1
            backend.active_connections -= 1
            backend.errors += 1
            writer.close()
            return

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter, is_upload: bool):
            try:
                while True:
                    data = await src.read(8192)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
                    # Track bandwidth
                    nbytes = len(data)
                    if is_upload:
                        backend.bytes_up += nbytes
                        self.bytes_up += nbytes
                    else:
                        backend.bytes_down += nbytes
                        self.bytes_down += nbytes
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        try:
            await asyncio.gather(
                pipe(reader, up_writer, is_upload=True),
                pipe(up_reader, writer, is_upload=False),
            )
        finally:
            self.active_connections -= 1
            backend.active_connections -= 1
            self._log(f"Connection closed: {peer_str} (config #{backend.config_id})")

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _speed_loop(self):
        """Periodically calculate throughput rates."""
        while self._running:
            await asyncio.sleep(2)
            now = time.monotonic()
            dt = now - self._prev_speed_ts
            if dt > 0:
                self._up_kbps = (self.bytes_up - self._prev_bytes_up) / dt / 1024
                self._down_kbps = (self.bytes_down - self._prev_bytes_down) / dt / 1024
                self._prev_bytes_up = self.bytes_up
                self._prev_bytes_down = self.bytes_down
                self._prev_speed_ts = now

    async def _ping_loop(self):
        """Periodically ping backends to measure latency."""
        while self._running:
            await asyncio.sleep(10)
            for backend in list(self._backends.values()):
                try:
                    start = time.monotonic()
                    r, w = await asyncio.wait_for(
                        asyncio.open_connection(backend.address, backend.port),
                        timeout=5,
                    )
                    elapsed = (time.monotonic() - start) * 1000
                    backend.ping_ms = elapsed
                    w.close()
                    try:
                        await w.wait_closed()
                    except Exception:
                        pass
                except Exception:
                    backend.ping_ms = None

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    async def _select_backend(self) -> _BackendStats | None:
        """Pick a backend based on the configured strategy."""
        config = await self._load_config()
        strategy = config.strategy if config else "round_robin"

        # Fetch healthy running configs with socks_port
        async with async_session() as session:
            result = await session.execute(
                select(Configuration)
                .where(Configuration.status == "running")
                .where(Configuration.health == "healthy")
                .where(Configuration.socks_port.isnot(None))
            )
            configs = list(result.scalars().all())

        if not configs:
            # Also try running but unknown health (freshly started)
            async with async_session() as session:
                result = await session.execute(
                    select(Configuration)
                    .where(Configuration.status == "running")
                    .where(Configuration.socks_port.isnot(None))
                )
                configs = list(result.scalars().all())

        if not configs:
            return None

        # Update backend tracking
        active_ids = {c.id for c in configs}
        # Remove stale backends
        for bid in list(self._backends.keys()):
            if bid not in active_ids:
                del self._backends[bid]
        # Add new backends
        for c in configs:
            if c.id not in self._backends:
                self._backends[c.id] = _BackendStats(
                    c.id, c.socks_address, c.socks_port
                )
            else:
                # Update address/port in case they changed
                self._backends[c.id].address = c.socks_address
                self._backends[c.id].port = c.socks_port

        backends = list(self._backends.values())

        if strategy == "round_robin":
            b = backends[self._rr_index % len(backends)]
            self._rr_index += 1
            return b
        elif strategy == "least_connections":
            return min(backends, key=lambda b: b.active_connections)
        elif strategy == "least_latency":
            # Use latency from health checker metrics if available
            with_latency = [b for b in backends if b.latency_ms is not None]
            if with_latency:
                return min(with_latency, key=lambda b: b.latency_ms)
            return random.choice(backends)

        return random.choice(backends)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self._logs.append(f"[{ts}] {message}")

    async def _load_config(self) -> DataBalancerConfig | None:
        async with async_session() as session:
            result = await session.execute(select(DataBalancerConfig))
            return result.scalar_one_or_none()


# Module-level singleton
data_balancer_manager = DataBalancerManager()
