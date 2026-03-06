"""System monitor — collects CPU, RAM, disk, and network stats via psutil."""

from __future__ import annotations

import asyncio
import logging
import time

import psutil

from app.schemas.system import SystemStats

logger = logging.getLogger(__name__)


class SystemMonitor:
    """Collects system resource stats at a configurable interval."""

    def __init__(self) -> None:
        self._latest: SystemStats | None = None
        self._prev_net: tuple[int, int] | None = None
        self._prev_time: float | None = None
        self._boot_time: float = psutil.boot_time()

    @property
    def latest(self) -> SystemStats | None:
        return self._latest

    def snapshot(self) -> SystemStats:
        """Take a synchronous snapshot of system stats."""
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        load = psutil.getloadavg()
        now = time.time()

        # Calculate network rate
        sent_rate = 0.0
        recv_rate = 0.0
        if self._prev_net and self._prev_time:
            dt = now - self._prev_time
            if dt > 0:
                sent_rate = ((net.bytes_sent - self._prev_net[0]) / 1024) / dt
                recv_rate = ((net.bytes_recv - self._prev_net[1]) / 1024) / dt

        self._prev_net = (net.bytes_sent, net.bytes_recv)
        self._prev_time = now

        stats = SystemStats(
            cpu_percent=cpu,
            memory_percent=mem.percent,
            memory_used_mb=mem.used / (1024 * 1024),
            memory_total_mb=mem.total / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 ** 3),
            disk_total_gb=disk.total / (1024 ** 3),
            net_sent_bytes=net.bytes_sent,
            net_recv_bytes=net.bytes_recv,
            net_sent_rate_kbps=round(sent_rate, 2),
            net_recv_rate_kbps=round(recv_rate, 2),
            uptime_seconds=now - self._boot_time,
            load_avg_1=load[0],
            load_avg_5=load[1],
            load_avg_15=load[2],
        )
        self._latest = stats
        return stats

    async def async_snapshot(self) -> SystemStats:
        """Run snapshot in executor to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.snapshot)


# Module-level singleton
system_monitor = SystemMonitor()
