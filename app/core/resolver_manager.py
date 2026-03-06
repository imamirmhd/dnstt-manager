"""Resolver manager — periodic testing, ranking, and smart assignment."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
import datetime

import aiohttp
import dnslib
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.resolver import Resolver
from app.models.metrics import ResolverMetricSnapshot
from app.models.configuration import Configuration

logger = logging.getLogger(__name__)


class ResolverManager:
    """Tests resolvers periodically and auto-assigns the best to smart-mode configs."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("ResolverManager started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ResolverManager stopped")

    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_checks()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Resolver check error: %s", exc)
            await asyncio.sleep(settings.resolver_check_interval)

    async def _run_checks(self) -> None:
        async with async_session() as session:
            result = await session.execute(select(Resolver))
            resolvers = list(result.scalars().all())

        if not resolvers:
            return

        # Set all resolvers to "checking" status
        async with async_session() as session:
            for resolver in resolvers:
                res = await session.execute(
                    select(Resolver).where(Resolver.id == resolver.id)
                )
                r = res.scalar_one_or_none()
                if r:
                    r.status = "checking"
            await session.commit()

        # Test all in parallel
        results = await asyncio.gather(
            *[self._test_resolver(r) for r in resolvers],
            return_exceptions=True,
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        dead_cutoff = now - datetime.timedelta(hours=settings.resolver_dead_threshold_hours)

        async with async_session() as session:
            for resolver, test_result in zip(resolvers, results):
                if isinstance(test_result, Exception):
                    latency = None
                    success = False
                else:
                    latency, success = test_result

                # Save metric snapshot
                snapshot = ResolverMetricSnapshot(
                    resolver_id=resolver.id,
                    latency_ms=latency,
                    success=success,
                    dns_query_time_ms=latency,
                )
                session.add(snapshot)

                # Update resolver stats
                res = await session.execute(
                    select(Resolver).where(Resolver.id == resolver.id)
                )
                r = res.scalar_one_or_none()
                if r is None:
                    continue

                r.total_checks += 1
                if success:
                    r.last_success_at = now
                    r.last_latency_ms = latency
                    # A successful check always revives from dead
                    r.status = "active"
                else:
                    r.failed_checks += 1

                # Calculate success rate
                if r.total_checks > 0:
                    r.success_rate = 1.0 - (r.failed_checks / r.total_checks)

                last_success = r.last_success_at
                # SQLite datetimes might be loaded as offset-naive
                if last_success and last_success.tzinfo is None:
                    last_success = last_success.replace(tzinfo=datetime.timezone.utc)

                # Mark dead only if:
                #  - we have a last_success and it's older than threshold, OR
                #  - we have never succeeded AND at least 10 checks done
                if last_success and last_success < dead_cutoff:
                    r.status = "dead"
                elif last_success is None and r.total_checks >= 10:
                    r.status = "dead"

            await session.commit()

        # Smart assignment
        await self._smart_assign()

    async def test_single(self, resolver_id: int) -> dict:
        """Manually test a single resolver and update its status."""
        async with async_session() as session:
            result = await session.execute(
                select(Resolver).where(Resolver.id == resolver_id)
            )
            resolver = result.scalar_one_or_none()
            if resolver is None:
                return {"ok": False, "message": "Resolver not found"}

            test_result = await self._test_resolver(resolver)
            now = datetime.datetime.now(datetime.timezone.utc)

            if isinstance(test_result, Exception):
                latency, success = None, False
            else:
                latency, success = test_result

            # Save metric
            snapshot = ResolverMetricSnapshot(
                resolver_id=resolver.id,
                latency_ms=latency,
                success=success,
                dns_query_time_ms=latency,
            )
            session.add(snapshot)

            resolver.total_checks += 1
            if success:
                resolver.last_success_at = now
                resolver.last_latency_ms = latency
                resolver.status = "active"
            else:
                resolver.failed_checks += 1

            if resolver.total_checks > 0:
                resolver.success_rate = 1.0 - (resolver.failed_checks / resolver.total_checks)

            await session.commit()

            if success:
                return {"ok": True, "message": f"Success — latency {latency:.1f}ms", "latency_ms": latency}
            else:
                return {"ok": False, "message": "Test failed — resolver did not respond"}

    def _parse_host_port(self, address: str, default_port: int) -> tuple[str, int]:
        addr = address.strip()
        if addr.startswith("[") and "]:" in addr:
            h, p = addr.rsplit(":", 1)
            return h.strip("[]"), int(p)
        elif addr.count(":") == 1:
            h, p = addr.rsplit(":", 1)
            return h, int(p)
        else:
            return addr.strip("[]"), default_port

    async def _test_resolver(self, resolver: Resolver) -> tuple[float | None, bool]:
        """Test a resolver by performing a real DNS probe."""
        start = time.monotonic()
        try:
            domain = "google.com"
            q = dnslib.DNSRecord.question(domain, "A").pack()
            
            if resolver.resolver_type == "doh":
                # DoH test: send a standard DNS query over HTTPS GET
                url = resolver.address
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                
                import base64
                b64_url = base64.urlsafe_b64encode(q).decode('utf-8').rstrip("=")
                
                if "?" not in url:
                    url = url.rstrip("/") + f"?dns={b64_url}"
                else:
                    url = url.rstrip("&") + f"&dns={b64_url}"
                    
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as client:
                    async with client.get(
                        url,
                        headers={"Accept": "application/dns-message"},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            ans = dnslib.DNSRecord.parse(data)
                            if len(ans.rr) > 0:
                                elapsed = (time.monotonic() - start) * 1000
                                return elapsed, True
                        return None, False

            elif resolver.resolver_type == "dot":
                # DoT test: TLS connection to resolver
                host, port = self._parse_host_port(resolver.address, 853)
                import struct
                q_len = struct.pack("!H", len(q))
                
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, ssl=True),
                    timeout=5,
                )
                writer.write(q_len + q)
                await writer.drain()
                
                len_data = await asyncio.wait_for(reader.readexactly(2), timeout=2)
                resp_len = struct.unpack("!H", len_data)[0]
                resp_data = await asyncio.wait_for(reader.readexactly(resp_len), timeout=2)
                
                writer.close()
                await writer.wait_closed()
                
                ans = dnslib.DNSRecord.parse(resp_data)
                if len(ans.rr) > 0:
                    elapsed = (time.monotonic() - start) * 1000
                    return elapsed, True
                return None, False

            elif resolver.resolver_type == "udp":
                # UDP DNS test
                host, port = self._parse_host_port(resolver.address, 53)
                loop = asyncio.get_running_loop()
                
                class DnsUdpProtocol(asyncio.DatagramProtocol):
                    def __init__(self):
                        self.future = loop.create_future()
                    def connection_made(self, transport):
                        self.transport = transport
                        transport.sendto(q)
                    def datagram_received(self, data, addr):
                        if not self.future.done():
                            self.future.set_result(data)
                    def error_received(self, exc):
                        if not self.future.done():
                            self.future.set_exception(exc)

                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: DnsUdpProtocol(),
                    remote_addr=(host, port)
                )
                try:
                    data = await asyncio.wait_for(protocol.future, timeout=2.0)
                    ans = dnslib.DNSRecord.parse(data)
                    if len(ans.rr) > 0:
                        elapsed = (time.monotonic() - start) * 1000
                        return elapsed, True
                    return None, False
                finally:
                    transport.close()

        except Exception as exc:
            logger.debug("Resolver %s test failed: %s", resolver.name, exc)
            return None, False

        return None, False

    async def _smart_assign(self) -> None:
        """Assign the best active resolver to configs in smart mode."""
        async with async_session() as session:
            # Find best active resolver (lowest latency, highest success rate)
            result = await session.execute(
                select(Resolver)
                .where(Resolver.status == "active")
                .where(Resolver.last_latency_ms.isnot(None))
                .order_by(Resolver.last_latency_ms.asc())
            )
            best = result.scalars().first()
            if best is None:
                return

            # Assign to all smart-mode configs
            await session.execute(
                update(Configuration)
                .where(Configuration.resolver_mode == "smart")
                .values(resolver_id=best.id)
            )
            await session.commit()
            logger.debug("Smart-assigned resolver %s (latency=%.1fms)", best.name, best.last_latency_ms or 0)


# Module-level singleton
resolver_manager = ResolverManager()
