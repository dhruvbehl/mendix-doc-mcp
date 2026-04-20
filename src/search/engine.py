"""SQLite FTS5 search engine with BM25 ranking for Mendix documentation."""

import re
import sqlite3
from pathlib import Path

from .models import Category, DocPage, SearchResult

# Characters that have special meaning in FTS5 query syntax and must be escaped
_FTS5_SPECIAL = re.compile(r'[":*^${}()\[\]~@#&|!\\]')

# Maximum content length returned by get_page (50,000 chars as per PRD)
MAX_CONTENT_LENGTH = 50_000


def _sanitize_fts5_query(query: str) -> str:
    """Sanitize a user query for safe use in FTS5 MATCH expressions.

    Escapes special characters and converts to prefix-match tokens so that
    partial words still match (e.g. 'micro' matches 'microflow').
    """
    # Strip special characters that would break FTS5 syntax
    cleaned = _FTS5_SPECIAL.sub(" ", query)
    # Split into tokens, drop empties
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return '""'
    # Each token gets a prefix wildcard for partial matching
    return " ".join(f"{token}*" for token in tokens)


class SearchEngine:
    """Read-only search engine backed by a SQLite FTS5 database.

    The database is expected to have been built by ``src.indexer.builder``.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # -- connection management -------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Read-only optimizations
            self._conn.execute("PRAGMA query_only = ON")
            self._conn.execute("PRAGMA cache_size = -10000")  # 10 MB cache
            self._conn.execute("PRAGMA mmap_size = 268435456")  # 256 MB mmap
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- public API ------------------------------------------------------------

    def search(
        self,
        query: str,
        version: str = "11",
        limit: int = 5,
    ) -> list[SearchResult]:
        """Full-text search with BM25 ranking and version filtering.

        Parameters
        ----------
        query:
            Free-text search query.
        version:
            Studio Pro version to filter on ('8', '9', '10', '11').
            Pages marked version='all' are always included.
        limit:
            Maximum number of results (capped at 20).

        Returns
        -------
        list[SearchResult]
            Ranked results, best match first.
        """
        limit = min(max(limit, 1), 20)
        fts_query = _sanitize_fts5_query(query)
        if fts_query == '""':
            return []

        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT p.path, p.title, p.url, p.section, p.version,
                   snippet(pages_fts, 2, '**', '**', '...', 48) AS snippet,
                   bm25(pages_fts, 3.0, 2.0, 1.0) AS score
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
              AND (p.version = ? OR p.version = 'all')
            ORDER BY score
            LIMIT ?
            """,
            (fts_query, version, limit),
        ).fetchall()

        return [
            SearchResult(
                title=row["title"],
                path=row["path"],
                url=row["url"],
                section=row["section"],
                version=row["version"],
                snippet=row["snippet"] or "",
                score=row["score"],
            )
            for row in rows
        ]

    def get_page(self, path: str) -> DocPage | None:
        """Retrieve the full content of a documentation page by its path.

        The *path* parameter can be a doc path (``/refguide/microflow/``) or a
        full URL (``https://docs.mendix.com/refguide/microflow/``).  Both forms
        are normalised before lookup.
        """
        path = self._normalise_path(path)
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT title, content, url, version, breadcrumb, last_modified
            FROM pages
            WHERE path = ?
            """,
            (path,),
        ).fetchone()

        if row is None:
            return None

        content = row["content"]
        if len(content) > MAX_CONTENT_LENGTH:
            content = (
                content[:MAX_CONTENT_LENGTH]
                + "\n\n[Content truncated — full page available at "
                + row["url"]
                + "]"
            )

        return DocPage(
            title=row["title"],
            content=content,
            url=row["url"],
            version=row["version"],
            breadcrumb=row["breadcrumb"] or "",
            last_modified=row["last_modified"] or "",
        )

    def list_categories(
        self,
        path: str = "/",
        version: str = "11",
    ) -> list[Category]:
        """List child categories/pages under *path* for a given version.

        Categories with version='all' are always included.
        """
        path = path.rstrip("/") + "/" if path != "/" else "/"
        conn = self._get_conn()

        if path == "/":
            # Top-level: return root categories
            rows = conn.execute(
                """
                SELECT path, title, description, child_count
                FROM categories
                WHERE parent_path IS NULL
                  AND (version = ? OR version = 'all')
                ORDER BY weight, title
                """,
                (version,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT path, title, description, child_count
                FROM categories
                WHERE parent_path = ?
                  AND (version = ? OR version = 'all')
                ORDER BY weight, title
                """,
                (path, version),
            ).fetchall()

        return [
            Category(
                title=row["title"],
                path=row["path"],
                type="category" if row["child_count"] > 0 else "page",
                description=row["description"] or "",
                child_count=row["child_count"],
            )
            for row in rows
        ]

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _normalise_path(path: str) -> str:
        """Turn a URL or path into the canonical ``/section/page/`` form."""
        # Strip full URL prefix if present
        if path.startswith("https://docs.mendix.com"):
            path = path[len("https://docs.mendix.com"):]
        if path.startswith("http://docs.mendix.com"):
            path = path[len("http://docs.mendix.com"):]
        # Ensure leading and trailing slashes
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path = path + "/"
        return path
