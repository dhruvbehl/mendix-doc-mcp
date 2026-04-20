"""Entry point for the Mendix Documentation MCP Server.

Usage:
    python -m src.server              # stdio (default)
    python -m src.server stdio        # explicit stdio
    python -m src.server http         # Streamable HTTP on port 8080

    uvx mendix-doc-mcp                # stdio via uvx (auto-builds index on first run)
"""

from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    """Start the MCP server with the requested transport."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from src.server.tools import mcp

    if len(sys.argv) > 1:
        transport = sys.argv[1]
    else:
        transport = os.environ.get("MCP_TRANSPORT", "stdio")

    port = int(os.environ.get("MCP_PORT", "8080"))

    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
