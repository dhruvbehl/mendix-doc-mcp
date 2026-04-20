"""MCP tool definitions for the Mendix Documentation server.

Exposes exactly 3 tools following ADR-005:
  - search_mendix_docs
  - get_mendix_doc
  - list_mendix_doc_categories
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.search.engine import SearchEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP application instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "mendix-docs",
    instructions=(
        "Mendix Documentation server. Use these tools to search, retrieve, and "
        "browse the official Mendix documentation (docs.mendix.com). The docs "
        "cover Studio Pro versions 8 through 11."
    ),
)

# ---------------------------------------------------------------------------
# Cache directory — stores the cloned repo and built DB
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    """Platform-appropriate cache directory."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "mendix-doc-mcp"


_DEFAULT_DB = _cache_dir() / "mendix-docs.db"
_DEFAULT_REPO = _cache_dir() / "mendix-docs-repo"

# ---------------------------------------------------------------------------
# Auto-build: clone + index if DB is missing or stale
# ---------------------------------------------------------------------------

def _ensure_index(db_path: Path, repo_path: Path) -> None:
    """Clone the mendix/docs repo and build the FTS5 index if the DB doesn't exist."""
    if db_path.exists():
        return

    logger.info("No index found at %s — building from mendix/docs repo...", db_path)
    print(
        "mendix-doc-mcp: First run — cloning Mendix docs and building search index. "
        "This takes about 70 seconds...",
        file=sys.stderr,
    )

    from src.indexer.clone import sync_repo
    from src.indexer.builder import build_index

    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    sync_repo(repo_path)
    count = build_index(repo_path, db_path)

    print(f"mendix-doc-mcp: Index ready — {count} pages indexed.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Search engine singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_engine() -> SearchEngine:
    db_path = Path(os.environ.get("MENDIX_DOCS_DB", str(_DEFAULT_DB)))
    repo_path = Path(os.environ.get("MENDIX_DOCS_REPO", str(_DEFAULT_REPO)))
    _ensure_index(db_path, repo_path)
    return SearchEngine(str(db_path))


# ---------------------------------------------------------------------------
# Tool 1: search_mendix_docs
# ---------------------------------------------------------------------------


@mcp.tool()
def search_mendix_docs(
    query: str,
    version: str = "11",
    max_results: int = 5,
) -> list[dict]:
    """Search Mendix documentation by keyword. Returns ranked results with snippets.

    Use this when a developer asks about any Mendix feature, API, widget, or
    configuration. Results are ranked by relevance using BM25.

    Args:
        query: Search query — keywords or short phrase (e.g. "microflow REST call").
        version: Studio Pro version to filter on: "8", "9", "10", or "11" (default).
        max_results: Maximum number of results to return (1-20, default 5).
    """
    engine = _get_engine()
    results = engine.search(query=query, version=version, limit=max_results)
    return [r.model_dump() for r in results]


# ---------------------------------------------------------------------------
# Tool 2: get_mendix_doc
# ---------------------------------------------------------------------------


@mcp.tool()
def get_mendix_doc(
    path: str,
    version: str = "11",
) -> dict:
    """Retrieve the full content of a specific Mendix documentation page.

    Use the path from search results or category listings. Accepts either a
    doc path (e.g. "/refguide/microflow/") or a full URL
    (e.g. "https://docs.mendix.com/refguide/microflow/").

    Args:
        path: Document path or full docs.mendix.com URL.
        version: Studio Pro version hint (used only if path is ambiguous).
    """
    engine = _get_engine()
    page = engine.get_page(path)
    if page is None:
        return {"error": f"Page not found: {path}"}
    return page.model_dump()


# ---------------------------------------------------------------------------
# Tool 3: list_mendix_doc_categories
# ---------------------------------------------------------------------------


@mcp.tool()
def list_mendix_doc_categories(
    version: str = "11",
) -> list[dict]:
    """Browse the Mendix documentation hierarchy.

    Returns the top-level category tree for discovering available content.
    Use paths from the results to drill deeper with another call, or to
    retrieve a specific page with get_mendix_doc.

    Args:
        version: Studio Pro version: "8", "9", "10", or "11" (default).
    """
    engine = _get_engine()
    categories = engine.list_categories(path="/", version=version)
    return [c.model_dump() for c in categories]
