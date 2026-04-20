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

_STALE_DAYS = 7


def _repo_is_stale(repo_path: Path) -> bool:
    """Check if the local repo clone is older than _STALE_DAYS."""
    import time
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return True
    fetch_head = git_dir / "FETCH_HEAD"
    ref_file = fetch_head if fetch_head.exists() else git_dir / "HEAD"
    age_days = (time.time() - ref_file.stat().st_mtime) / 86400
    return age_days > _STALE_DAYS


def _ensure_index(db_path: Path, repo_path: Path) -> None:
    """Clone + build if DB missing. Pull + rebuild if repo stale (>7 days)."""
    from src.indexer.clone import sync_repo
    from src.indexer.builder import build_index

    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        logger.info("No index found — building from mendix/docs repo...")
        print(
            "mendix-doc-mcp: First run — cloning Mendix docs and building search index. "
            "This takes about 70 seconds...",
            file=sys.stderr,
        )
        sync_repo(repo_path)
        count = build_index(repo_path, db_path)
        print(f"mendix-doc-mcp: Index ready — {count} pages indexed.", file=sys.stderr)
        return

    if _repo_is_stale(repo_path):
        logger.info("Repo older than %d days — checking for updates...", _STALE_DAYS)
        changed = sync_repo(repo_path)
        if changed:
            logger.info("%d files changed — rebuilding index...", len(changed))
            print(f"mendix-doc-mcp: Docs updated, rebuilding index...", file=sys.stderr)
            count = build_index(repo_path, db_path)
            print(f"mendix-doc-mcp: Index refreshed — {count} pages.", file=sys.stderr)
        else:
            logger.info("No changes. Index is current.")


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
