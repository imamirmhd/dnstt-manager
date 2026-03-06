#!/usr/bin/env python3
"""DNS Tunnel Manager — CLI entry point."""

from __future__ import annotations

import logging
import sys

import click
import uvicorn

from app.config import settings


@click.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Host address to bind to.")
@click.option("--port", "-p", default=8080, show_default=True, help="Port to listen on.")
@click.option("--user", "-u", default=None, help="Username for panel authentication (optional).")
@click.option("--password", "--pass", default=None, help="Password for panel authentication (optional).")
@click.option(
    "--dnstt-path",
    default="dnstt-client",
    show_default=True,
    help="Path to the dnstt-client binary.",
)
@click.option(
    "--slipstream-path",
    default="slipstream-client",
    show_default=True,
    help="Path to the slipstream-client binary.",
)
@click.option("--log-level", default="info", show_default=True, help="Logging level (debug/info/warning/error).")
def main(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    dnstt_path: str,
    slipstream_path: str,
    log_level: str,
):
    """DNS Tunnel Manager — manage dnstt & slipstream tunnel configurations.

    Start the web dashboard and API server. Optionally protect the panel
    with HTTP Basic authentication by passing --user and --password.

    Examples:

      \b
      python main.py
      python main.py --host 127.0.0.1 --port 9090
      python main.py -u admin --pass secret
      python main.py --dnstt-path /usr/local/bin/dnstt-client
    """
    # Apply settings
    settings.host = host
    settings.port = port
    settings.username = user
    settings.password = password
    settings.dnstt_client_path = dnstt_path
    settings.slipstream_client_path = slipstream_path

    # Logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        stream=sys.stdout,
    )

    click.echo(f"🚀 DNS Tunnel Manager starting on http://{host}:{port}")
    if user:
        click.echo(f"🔒 Authentication enabled (user: {user})")

    uvicorn.run(
        "app.api.app:create_app",
        host=host,
        port=port,
        factory=True,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
