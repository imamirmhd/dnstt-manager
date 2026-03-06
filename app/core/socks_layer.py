"""SOCKS5 proxy layer — provides a uniform SOCKS5 endpoint per configuration.

For SOCKS5 backends: creates a TCP relay from socks_port → tunnel listen_port.
For SSH   backends: spawns `ssh -D socks_port -N` through the tunnel to create
                    a dynamic SOCKS5 proxy.

This gives HAProxy (and the user) a single, consistent SOCKS5 interface
regardless of the underlying backend type.
"""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.configuration import Configuration

logger = logging.getLogger(__name__)


class _SocksLayerState:
    """Runtime state for one managed SOCKS5 proxy."""

    def __init__(self, config_id: int):
        self.config_id = config_id
        self.server: asyncio.Server | None = None  # TCP relay server
        self.ssh_process: asyncio.subprocess.Process | None = None
        self.running = False
        # Bandwidth counters
        self.bytes_up: int = 0
        self.bytes_down: int = 0
        self._last_sample_time: float = time.monotonic()
        self._last_bytes_up: int = 0
        self._last_bytes_down: int = 0

    def get_speeds(self) -> dict:
        """Calculate current upload/download speeds in KB/s."""
        now = time.monotonic()
        elapsed = now - self._last_sample_time
        if elapsed < 0.5:
            elapsed = 0.5  # Avoid division by zero or unrealistic spikes

        up_speed = (self.bytes_up - self._last_bytes_up) / 1024 / elapsed
        down_speed = (self.bytes_down - self._last_bytes_down) / 1024 / elapsed

        self._last_sample_time = now
        self._last_bytes_up = self.bytes_up
        self._last_bytes_down = self.bytes_down

        return {
            "bytes_up": self.bytes_up,
            "bytes_down": self.bytes_down,
            "up_kbps": round(up_speed, 1),
            "down_kbps": round(down_speed, 1),
        }


class SocksLayerManager:
    """Manages per-configuration SOCKS5 proxy endpoints."""

    def __init__(self) -> None:
        self._states: dict[int, _SocksLayerState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, config_id: int) -> dict:
        """Start the managed SOCKS5 proxy for a given config."""
        async with self._lock:
            cfg = await self._load_config(config_id)
            if cfg is None:
                return {"ok": False, "message": "Config not found"}
            if cfg.socks_port is None:
                return {"ok": False, "message": "No socks_port configured"}

            state = self._states.get(config_id)
            if state and state.running:
                return {"ok": False, "message": "SOCKS proxy already running"}

            state = _SocksLayerState(config_id)
            self._states[config_id] = state

            try:
                if cfg.backend_type == "socks5":
                    await self._start_tcp_relay(cfg, state)
                elif cfg.backend_type == "ssh":
                    await self._start_ssh_proxy(cfg, state)
                else:
                    return {"ok": False, "message": f"Unknown backend: {cfg.backend_type}"}

                state.running = True

                # Save PID/state to DB
                socks_pid = state.ssh_process.pid if state.ssh_process else None
                await self._update_db(config_id, socks_pid=socks_pid)

                logger.info(
                    "SOCKS5 proxy for config %d started on %s:%d",
                    config_id, cfg.socks_address, cfg.socks_port,
                )
                return {"ok": True, "message": f"SOCKS5 proxy on {cfg.socks_address}:{cfg.socks_port}"}

            except Exception as exc:
                logger.exception("Failed to start SOCKS5 proxy for config %d: %s", config_id, exc)
                return {"ok": False, "message": str(exc)}

    async def stop(self, config_id: int) -> dict:
        """Stop the managed SOCKS5 proxy for a given config."""
        async with self._lock:
            state = self._states.get(config_id)
            if state is None or not state.running:
                return {"ok": False, "message": "Not running"}

            state.running = False

            # Stop TCP relay server
            if state.server:
                state.server.close()
                await state.server.wait_closed()
                state.server = None

            # Stop SSH process
            if state.ssh_process and state.ssh_process.returncode is None:
                state.ssh_process.terminate()
                try:
                    await asyncio.wait_for(state.ssh_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    state.ssh_process.kill()
                state.ssh_process = None

            await self._update_db(config_id, socks_pid=None)
            logger.info("SOCKS5 proxy for config %d stopped", config_id)
            return {"ok": True, "message": "SOCKS proxy stopped"}

    async def stop_all(self) -> None:
        for cid in list(self._states.keys()):
            await self.stop(cid)

    def is_running(self, config_id: int) -> bool:
        state = self._states.get(config_id)
        return bool(state and state.running)

    def get_bandwidth(self, config_id: int) -> dict | None:
        """Get bandwidth stats for a configuration's SOCKS proxy."""
        state = self._states.get(config_id)
        if state is None or not state.running:
            return None
        return state.get_speeds()

    # ------------------------------------------------------------------
    # TCP relay (for SOCKS5 backends)
    # ------------------------------------------------------------------

    async def _start_tcp_relay(self, cfg: Configuration, state: _SocksLayerState) -> None:
        """Relay TCP connections from socks_port → tunnel listen_port.

        Since the tunnel already speaks SOCKS5, this is a simple byte-level relay.
        """
        upstream_host = cfg.listen_address
        upstream_port = cfg.listen_port

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                up_reader, up_writer = await asyncio.wait_for(
                    asyncio.open_connection(upstream_host, upstream_port),
                    timeout=10,
                )
            except Exception as exc:
                logger.debug("TCP relay: upstream connect failed: %s", exc)
                writer.close()
                return

            async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter, direction: str):
                try:
                    while True:
                        data = await src.read(8192)
                        if not data:
                            break
                        # Track bandwidth
                        if direction == "up":
                            state.bytes_up += len(data)
                        else:
                            state.bytes_down += len(data)
                        dst.write(data)
                        await dst.drain()
                except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                    pass
                finally:
                    try:
                        dst.close()
                    except Exception:
                        pass

            await asyncio.gather(
                pipe(reader, up_writer, "up"),
                pipe(up_reader, writer, "down"),
            )

        state.server = await asyncio.start_server(
            handle_client,
            host=cfg.socks_address,
            port=cfg.socks_port,
        )

    # ------------------------------------------------------------------
    # SSH dynamic proxy (for SSH backends)
    # ------------------------------------------------------------------

    async def _start_ssh_proxy(self, cfg: Configuration, state: _SocksLayerState) -> None:
        """Spawn `ssh -D socks_port -N` through the tunnel to create a SOCKS5 proxy.

        The tunnel (dnstt/slipstream) forwards TCP on listen_port → remote SSH.
        SSH -D creates a dynamic SOCKS5 proxy.
        """
        ssh_user = cfg.backend_user or "root"
        ssh_port = cfg.listen_port
        ssh_host = cfg.listen_address

        cmd = [
            "ssh",
            "-D", f"{cfg.socks_address}:{cfg.socks_port}",
            "-N",  # no remote command
            "-p", str(ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "ConnectTimeout=10",
            "-o", "ExitOnForwardFailure=yes",
        ]

        # Password auth via sshpass if password is provided
        if cfg.backend_password:
            cmd = ["sshpass", "-p", cfg.backend_password] + cmd

        cmd.append(f"{ssh_user}@{ssh_host}")

        logger.info("Starting SSH SOCKS proxy: %s", " ".join(cmd))

        state.ssh_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Brief wait to check for immediate failure
        await asyncio.sleep(1)
        if state.ssh_process.returncode is not None:
            stderr = b""
            if state.ssh_process.stderr:
                stderr = await state.ssh_process.stderr.read()
            raise RuntimeError(
                f"SSH proxy exited immediately (code {state.ssh_process.returncode}): "
                f"{stderr.decode(errors='replace')}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_config(self, config_id: int) -> Configuration | None:
        async with async_session() as session:
            result = await session.execute(
                select(Configuration).where(Configuration.id == config_id)
            )
            return result.scalar_one_or_none()

    async def _update_db(self, config_id: int, *, socks_pid: int | None = -1) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Configuration).where(Configuration.id == config_id)
            )
            cfg = result.scalar_one_or_none()
            if cfg and socks_pid != -1:
                cfg.socks_pid = socks_pid
            await session.commit()


# Module-level singleton
socks_layer_manager = SocksLayerManager()
