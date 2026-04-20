#!/usr/bin/env python3
"""CLI script to start the Mendix Documentation MCP server.

Usage:
    python scripts/serve.py                          # stdio, auto-builds index
    python scripts/serve.py --transport http          # HTTP on port 8080
    python scripts/serve.py --db ./data/mendix-docs.db  # use specific DB
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    help="MCP transport to use.",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the SQLite database. If omitted, auto-builds in cache dir.",
)
@click.option(
    "--port",
    type=int,
    default=8080,
    help="Port for HTTP transport (ignored for stdio).",
)
def main(transport: str, db: Path | None, port: int) -> None:
    """Start the Mendix Documentation MCP server."""
    if db is not None:
        os.environ["MENDIX_DOCS_DB"] = str(db.resolve())

    os.environ["MCP_TRANSPORT"] = transport
    os.environ["MCP_PORT"] = str(port)

    from src.server.tools import mcp

    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
