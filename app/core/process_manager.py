"""Process manager — spawns and manages dnstt / slipstream client subprocesses."""

from __future__ import annotations

import asyncio
import collections
import logging
import os
import tempfile
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.configuration import Configuration
from app.core.socks_layer import socks_layer_manager

logger = logging.getLogger(__name__)

# Rolling log buffer per configuration id
LOG_BUFFER_MAX = 500


class _ProcessState:
    """Runtime state for one tunnel process."""

    def __init__(self, config_id: int):
        self.config_id = config_id
        self.process: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task | None = None
        self.logs: collections.deque[str] = collections.deque(maxlen=LOG_BUFFER_MAX)
        self.restart_timestamps: list[float] = []
        self.should_run = False
        self.start_time: float = 0  # monotonic time when process was started
        self._temp_files: list[str] = []  # temp files to clean up


class ProcessManager:
    """Singleton-ish manager for all tunnel subprocesses."""

    def __init__(self) -> None:
        self._states: dict[int, _ProcessState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, config_id: int) -> dict[str, Any]:
        async with self._lock:
            state = self._states.get(config_id)
            if state and state.should_run:
                return {"ok": False, "message": "Already running"}

            if state is None:
                state = _ProcessState(config_id)
                self._states[config_id] = state

            state.should_run = True
            state.task = asyncio.create_task(self._run_loop(state))
            return {"ok": True, "message": "Starting"}

    async def stop(self, config_id: int) -> dict[str, Any]:
        async with self._lock:
            state = self._states.get(config_id)
            if state is None or not state.should_run:
                return {"ok": False, "message": "Not running"}

            state.should_run = False
            if state.process and state.process.returncode is None:
                state.process.terminate()
                try:
                    await asyncio.wait_for(state.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    state.process.kill()
            if state.task and not state.task.done():
                state.task.cancel()

            # Stop managed SOCKS proxy
            await socks_layer_manager.stop(config_id)

            # Clean up temp files (pubkey files, etc.)
            for f in state._temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            state._temp_files.clear()

            await self._update_db_status(config_id, status="stopped", pid=None)
            return {"ok": True, "message": "Stopped"}

    async def restart(self, config_id: int) -> dict[str, Any]:
        await self.stop(config_id)
        return await self.start(config_id)

    def get_logs(self, config_id: int) -> list[str]:
        state = self._states.get(config_id)
        if state is None:
            return []
        return list(state.logs)

    def clear_logs(self, config_id: int) -> None:
        """Clear the in-memory log buffer for a configuration."""
        state = self._states.get(config_id)
        if state:
            state.logs.clear()

    def is_running(self, config_id: int) -> bool:
        state = self._states.get(config_id)
        return bool(state and state.should_run and state.process and state.process.returncode is None)

    async def stop_all(self) -> None:
        for cid in list(self._states.keys()):
            await self.stop(cid)

    # ------------------------------------------------------------------
    # Internal run loop
    # ------------------------------------------------------------------

    async def _run_loop(self, state: _ProcessState) -> None:
        config_id = state.config_id
        attempt = 0

        while state.should_run:
            try:
                cfg = await self._load_config(config_id)
                if cfg is None:
                    logger.error("Config %d not found, stopping", config_id)
                    state.should_run = False
                    break

                cmd = self._build_command(cfg)
                logger.info("Starting config %d: %s", config_id, " ".join(cmd))
                state.logs.append(f"[start] {' '.join(cmd)}")

                await self._update_db_status(config_id, status="starting")

                state.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                state.start_time = time.monotonic()
                await self._update_db_status(config_id, status="running", pid=state.process.pid)

                # Start managed SOCKS5 proxy layer
                socks_result = await socks_layer_manager.start(config_id)
                if socks_result.get("ok"):
                    state.logs.append(f"[socks] {socks_result['message']}")
                else:
                    state.logs.append(f"[socks] warning: {socks_result.get('message', 'no socks_port')}")

                # Read output
                assert state.process.stdout is not None
                async for line_bytes in state.process.stdout:
                    line = line_bytes.decode(errors="replace").rstrip()
                    state.logs.append(line)

                exit_code = await state.process.wait()
                run_duration = time.monotonic() - state.start_time
                state.logs.append(f"[exit] code={exit_code} after {run_duration:.1f}s")
                logger.warning("Config %d exited with code %d after %.1fs", config_id, exit_code, run_duration)

                if not state.should_run:
                    break

                # Immediate-exit detection: if process dies within 3 seconds,
                # it means the config is broken (bad binary, bad args, etc.)
                if run_duration < 3.0:
                    logger.error("Config %d: crashed immediately (%.1fs), marking unhealthy", config_id, run_duration)
                    state.logs.append("[unhealthy] process crashed immediately — check binary path and config")
                    await self._update_db_status(config_id, status="error", health="unhealthy", pid=None)
                    state.should_run = False
                    break

                # Track restart timestamps
                now = time.monotonic()
                state.restart_timestamps.append(now)
                # Keep only timestamps within the window
                cutoff = now - settings.restart_window_seconds
                state.restart_timestamps = [t for t in state.restart_timestamps if t > cutoff]

                if len(state.restart_timestamps) >= settings.max_restart_attempts:
                    logger.error("Config %d: too many restarts, marking unhealthy", config_id)
                    state.logs.append("[unhealthy] too many rapid restarts")
                    await self._update_db_status(config_id, status="error", health="unhealthy", pid=None)
                    state.should_run = False
                    break

                # Exponential backoff
                attempt += 1
                delay = min(settings.restart_backoff_base ** attempt, 60)
                state.logs.append(f"[restart] attempt {attempt}, waiting {delay:.1f}s")
                await self._update_db_status(
                    config_id, status="starting", pid=None,
                    restart_count_increment=True,
                )
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except FileNotFoundError as exc:
                logger.error("Config %d binary not found: %s", config_id, exc)
                state.logs.append(f"[error] Binary not found. Please install it or update Settings. {exc}")
                await self._update_db_status(config_id, status="error", pid=None, health="unhealthy")
                state.should_run = False
                break
            except Exception as exc:
                logger.exception("Config %d error: %s", config_id, exc)
                state.logs.append(f"[error] {exc}")
                await self._update_db_status(config_id, status="error", pid=None)
                if state.should_run:
                    await asyncio.sleep(5)

        await self._update_db_status(config_id, status="stopped", pid=None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_command(self, cfg: Configuration) -> list[str]:
        """Build the CLI command for the tunnel client."""
        if cfg.transport_type == "dnstt":
            binary = settings.dnstt_client_path
            cmd = [binary]
            # Resolver will be injected by health checker / resolver manager
            # For now support manual resolver assignment
            if cfg.resolver and cfg.resolver.resolver_type == "doh":
                cmd += ["-doh", cfg.resolver.address]
            elif cfg.resolver and cfg.resolver.resolver_type == "dot":
                cmd += ["-dot", cfg.resolver.address]
            else:
                # Fallback to UDP 8.8.8.8
                cmd += ["-udp", "8.8.8.8:53"]

            if cfg.pubkey:
                # dnstt accepts -pubkey with hex string directly
                cmd += ["-pubkey", cfg.pubkey.strip()]

            cmd.append(cfg.domain)
            cmd.append(f"{cfg.listen_address}:{cfg.listen_port}")

        elif cfg.transport_type == "slipstream":
            binary = settings.slipstream_client_path
            cmd = [binary]

            # slipstream uses -d/--domain for domain
            cmd += ["-d", cfg.domain]

            # slipstream uses -r/--resolver with plain address (IP:port)
            if cfg.resolver:
                # For slipstream, the resolver is just an address like 8.8.8.8:53
                # regardless of DoH/DoT/UDP — slipstream handles the transport itself
                addr = cfg.resolver.address
                # Strip protocol prefix if present (the user might have a DoH URL stored)
                if addr.startswith("https://") or addr.startswith("http://"):
                    # DoH URL — pass as-is, slipstream might support it
                    cmd += ["-r", addr]
                else:
                    cmd += ["-r", addr]
            else:
                cmd += ["-r", "8.8.8.8:53"]

            # slipstream uses --cert PATH for certificate
            if cfg.cert_path:
                # cert_path holds pasted cert content — write to temp file
                tmp = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.pem', prefix='slipstream_cert_',
                    delete=False,
                )
                tmp.write(cfg.cert_path.strip())
                tmp.close()
                state = self._states.get(cfg.id)
                if state:
                    state._temp_files.append(tmp.name)
                cmd += ["--cert", tmp.name]

            # slipstream uses --tcp-listen-host and -l/--tcp-listen-port
            cmd += ["--tcp-listen-host", cfg.listen_address]
            cmd += ["-l", str(cfg.listen_port)]
        else:
            raise ValueError(f"Unknown transport: {cfg.transport_type}")

        return cmd

    async def _load_config(self, config_id: int) -> Configuration | None:
        async with async_session() as session:
            result = await session.execute(
                select(Configuration).where(Configuration.id == config_id)
            )
            return result.scalar_one_or_none()

    async def _update_db_status(
        self,
        config_id: int,
        *,
        status: str | None = None,
        health: str | None = None,
        pid: int | None = -1,  # sentinel: -1 means don't change
        restart_count_increment: bool = False,
    ) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Configuration).where(Configuration.id == config_id)
            )
            cfg = result.scalar_one_or_none()
            if cfg is None:
                return
            if status is not None:
                cfg.status = status
            if health is not None:
                cfg.health = health
            if pid != -1:
                cfg.pid = pid
            if restart_count_increment:
                cfg.restart_count += 1
            await session.commit()


# Module-level singleton
process_manager = ProcessManager()
