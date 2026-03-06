import asyncio
import logging
import random
import struct
import ssl
import base64
from typing import Callable
from dataclasses import dataclass

import aiohttp
from sqlalchemy import select
from app.database import async_session
from app.models.resolver import Resolver
from app.models.balancer import DnsBalancerConfig

logger = logging.getLogger(__name__)

@dataclass
class _CachedResolver:
    id: int
    resolver_type: str
    address: str
    last_latency_ms: float | None
    success_rate: float
    id: int
    resolver_type: str
    address: str
    last_latency_ms: float | None
    success_rate: float


from app.database import async_session
from app.models.resolver import Resolver
from app.models.balancer import DnsBalancerConfig

logger = logging.getLogger(__name__)


class DnsBalancerManager:
    """Manages a local DNS proxy with pluggable resolver selection."""

    def __init__(self) -> None:
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._dot_server: asyncio.Server | None = None
        self._doh_server: asyncio.Server | None = None
        self._running = False
        self._rr_index = 0  # round-robin counter
        self.queries_handled = 0
        self.queries_failed = 0
        self._client_tasks: set[asyncio.Task] = set()

        self._strategy: str = "least_latency"
        self._resolvers: list[_CachedResolver] = []
        self._sync_task: asyncio.Task | None = None

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
            return {"ok": False, "message": "No DNS balancer config found"}

        addr = config.listen_address
        errors = []

        # Start UDP listener
        if config.udp_port > 0:
            try:
                loop = asyncio.get_running_loop()
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _UdpDnsProtocol(self),
                    local_addr=(addr, config.udp_port),
                )
                self._udp_transport = transport
                logger.info("DNS Balancer UDP listening on %s:%d", addr, config.udp_port)
            except PermissionError as exc:
                errors.append(f"UDP Permission Denied (try running as root for port {config.udp_port}): {exc}")
                logger.warning("Permission denied starting DNS UDP on %s:%d", addr, config.udp_port)
            except Exception as exc:
                errors.append(f"UDP: {exc}")
                logger.exception("Failed to start DNS UDP on %s:%d", addr, config.udp_port)

        # Start DoT listener (plain TCP, TLS can be added later with certs)
        if config.dot_port > 0:
            try:
                self._dot_server = await asyncio.start_server(
                    self._handle_dot_client, addr, config.dot_port,
                )
                logger.info("DNS Balancer DoT listening on %s:%d", addr, config.dot_port)
            except Exception as exc:
                errors.append(f"DoT: {exc}")
                logger.exception("Failed to start DNS DoT on %s:%d", addr, config.dot_port)

        # Start DoH listener (simple HTTP)
        if config.doh_port > 0:
            try:
                self._doh_server = await asyncio.start_server(
                    self._handle_doh_client, addr, config.doh_port,
                )
                logger.info("DNS Balancer DoH listening on %s:%d", addr, config.doh_port)
            except Exception as exc:
                errors.append(f"DoH: {exc}")
                logger.exception("Failed to start DNS DoH on %s:%d", addr, config.doh_port)

        if not self._udp_transport and not self._dot_server and not self._doh_server:
            return {"ok": False, "message": f"All DNS listeners failed: {'; '.join(errors)}"}

        self._running = True
        
        # Start background sync
        self._sync_task = asyncio.create_task(self._sync_loop())

        msg = "DNS Balancer started"
        if errors:
            msg += f" (warnings: {'; '.join(errors)})"
        return {"ok": True, "message": msg}

    async def stop(self) -> dict:
        if not self._running:
            return {"ok": False, "message": "Not running"}

        if self._udp_transport:
            self._udp_transport.close()
            self._udp_transport = None

        if self._dot_server:
            self._dot_server.close()
            await self._dot_server.wait_closed()
            self._dot_server = None

        if self._doh_server:
            self._doh_server.close()
            await self._doh_server.wait_closed()
            self._doh_server = None

        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()

        self._running = False
        self._resolvers.clear()
        
        logger.info("DNS Balancer stopped")
        return {"ok": True, "message": "Stopped"}

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "udp_active": self._udp_transport is not None,
            "dot_active": self._dot_server is not None,
            "doh_active": self._doh_server is not None,
            "queries_handled": self.queries_handled,
            "queries_failed": self.queries_failed,
        }

    # ------------------------------------------------------------------
    # DNS forwarding
    # ------------------------------------------------------------------

    async def forward_query(self, query: bytes) -> bytes | None:
        """Forward a DNS query to the best available resolver."""
        resolver = await self._select_resolver()
        if resolver is None:
            logger.warning("No active resolvers available for DNS Balancer")
            return None

        self.queries_handled += 1

        try:
            if resolver.resolver_type == "udp":
                return await self._forward_udp(resolver.address, query)
            elif resolver.resolver_type == "doh":
                return await self._forward_doh(resolver.address, query)
            elif resolver.resolver_type == "dot":
                return await self._forward_dot(resolver.address, query)
        except Exception as exc:
            self.queries_failed += 1
            logger.debug("DNS forward to %s failed: %s", resolver.address, exc)
            return None

    async def _forward_udp(self, address: str, query: bytes) -> bytes:
        """Forward via UDP."""
        host, port_str = address.rsplit(":", 1)
        port = int(port_str)

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        class ResponseProtocol(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                if not future.done():
                    future.set_result(data)
            def error_received(self, exc):
                if not future.done():
                    future.set_exception(exc)

        transport, _ = await loop.create_datagram_endpoint(
            ResponseProtocol, remote_addr=(host, port)
        )
        try:
            transport.sendto(query)
            return await asyncio.wait_for(future, timeout=5)
        finally:
            transport.close()

    async def _forward_doh(self, url: str, query: bytes) -> bytes:
        """Forward via DNS-over-HTTPS (GET with base64url)."""
        b64 = base64.urlsafe_b64encode(query).rstrip(b"=").decode()
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            async with session.get(
                url, params={"dns": b64},
                headers={"Accept": "application/dns-message"},
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                raise RuntimeError(f"DoH returned {resp.status}")

    async def _forward_dot(self, address: str, query: bytes) -> bytes:
        """Forward via DNS-over-TLS."""
        host, port_str = address.rsplit(":", 1)
        port = int(port_str)
        ctx = ssl.create_default_context()

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx), timeout=5
        )
        try:
            # DoT uses a 2-byte length prefix
            writer.write(struct.pack("!H", len(query)) + query)
            await writer.drain()
            length_data = await asyncio.wait_for(reader.readexactly(2), timeout=5)
            length = struct.unpack("!H", length_data)[0]
            return await asyncio.wait_for(reader.readexactly(length), timeout=5)
        finally:
            writer.close()
            await writer.wait_closed()

    # ------------------------------------------------------------------
    # Resolver selection & Background Sync
    # ------------------------------------------------------------------

    async def _sync_loop(self):
        """Periodically sync config and active resolvers from the database."""
        while self._running:
            try:
                config = await self._load_config()
                if config:
                    self._strategy = config.strategy
                
                async with async_session() as session:
                    result = await session.execute(
                        select(Resolver).where(Resolver.status != "dead")
                    )
                    resolvers = list(result.scalars().all())
                    
                    # Update local cache safely
                    new_resolvers = [
                        _CachedResolver(
                            id=r.id,
                            resolver_type=r.resolver_type,
                            address=r.address,
                            last_latency_ms=r.last_latency_ms,
                            success_rate=r.success_rate
                        )
                        for r in resolvers
                    ]
                    self._resolvers = new_resolvers
                    
            except Exception as exc:
                logger.error("DNS Balancer sync error: %s", exc)
                
            await asyncio.sleep(5)

    async def _select_resolver(self) -> _CachedResolver | None:
        """Pick a resolver based on the configured strategy from memory."""
        resolvers = self._resolvers
        strategy = self._strategy

        if not resolvers:
            return None

        if strategy == "round_robin":
            r = resolvers[self._rr_index % len(resolvers)]
            self._rr_index += 1
            return r
        elif strategy == "least_latency":
            # Pick resolver with lowest latency; fall back to random if no data
            with_latency = [r for r in resolvers if r.last_latency_ms is not None]
            if with_latency:
                return min(with_latency, key=lambda r: r.last_latency_ms)
            return random.choice(resolvers)
        elif strategy == "weighted":
            # Weight by success rate
            weights = [max(r.success_rate, 0.01) for r in resolvers]
            return random.choices(resolvers, weights=weights, k=1)[0]

        return random.choice(resolvers)

    # ------------------------------------------------------------------
    # Protocol handlers
    # ------------------------------------------------------------------

    async def _handle_dot_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle a DoT (TCP) client connection."""
        try:
            while True:
                length_data = await asyncio.wait_for(reader.readexactly(2), timeout=30)
                length = struct.unpack("!H", length_data)[0]
                query = await asyncio.wait_for(reader.readexactly(length), timeout=10)
                response = await self.forward_query(query)
                if response:
                    writer.write(struct.pack("!H", len(response)) + response)
                    await writer.drain()
                else:
                    break
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError):
            pass
        finally:
            writer.close()

    async def _handle_doh_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle a simple DoH (HTTP) listener."""
        try:
            # Read HTTP request
            raw = await asyncio.wait_for(reader.read(4096), timeout=10)
            if not raw:
                writer.close()
                return

            request_line = raw.split(b"\r\n", 1)[0].decode(errors="replace")
            parts = request_line.split()
            if len(parts) < 2:
                writer.close()
                return

            method, path = parts[0], parts[1]

            if method == "GET" and "dns=" in path:
                # Extract ?dns= parameter
                query_string = path.split("?", 1)[1] if "?" in path else ""
                params = dict(p.split("=", 1) for p in query_string.split("&") if "=" in p)
                b64 = params.get("dns", "")
                # Add padding
                b64 += "=" * (4 - len(b64) % 4) if len(b64) % 4 else ""
                dns_query = base64.urlsafe_b64decode(b64)
            elif method == "POST":
                # Body is after \r\n\r\n
                body_start = raw.find(b"\r\n\r\n")
                dns_query = raw[body_start + 4:] if body_start >= 0 else b""
            else:
                # Return 400
                resp = b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"
                writer.write(resp)
                await writer.drain()
                writer.close()
                return

            response = await self.forward_query(dns_query)
            if response:
                http_resp = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/dns-message\r\n"
                    b"Content-Length: " + str(len(response)).encode() + b"\r\n"
                    b"\r\n" + response
                )
            else:
                http_resp = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n"

            writer.write(http_resp)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_config(self) -> DnsBalancerConfig | None:
        async with async_session() as session:
            result = await session.execute(select(DnsBalancerConfig))
            return result.scalar_one_or_none()


class _UdpDnsProtocol(asyncio.DatagramProtocol):
    """UDP DNS listener protocol."""

    def __init__(self, manager: DnsBalancerManager):
        self._manager = manager

    def connection_made(self, transport: asyncio.DatagramTransport):
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        task = asyncio.create_task(self._handle(data, addr))
        self._manager._client_tasks.add(task)
        task.add_done_callback(self._manager._client_tasks.discard)

    async def _handle(self, data: bytes, addr: tuple):
        response = await self._manager.forward_query(data)
        if response and self._transport:
            self._transport.sendto(response, addr)


# Module-level singleton
dns_balancer_manager = DnsBalancerManager()
