"""SQLite database builder — creates the FTS5 index from parsed Mendix docs."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .parser import parse_doc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema (ADR-003)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Main content table
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    content     TEXT NOT NULL,
    version     TEXT NOT NULL,
    section     TEXT NOT NULL,
    breadcrumb  TEXT,
    url         TEXT NOT NULL,
    last_modified TEXT,
    word_count  INTEGER
);

-- FTS5 virtual table with porter stemmer and column weights
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title,
    description,
    content,
    content='pages',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS5 in sync with the pages table
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, description, content)
    VALUES (new.id, new.title, new.description, new.content);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, description, content)
    VALUES ('delete', old.id, old.title, old.description, old.content);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, description, content)
    VALUES ('delete', old.id, old.title, old.description, old.content);
    INSERT INTO pages_fts(rowid, title, description, content)
    VALUES (new.id, new.title, new.description, new.content);
END;

-- Category hierarchy for browsing
CREATE TABLE IF NOT EXISTS categories (
    path        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    parent_path TEXT,
    version     TEXT NOT NULL,
    description TEXT,
    child_count INTEGER DEFAULT 0,
    weight      INTEGER DEFAULT 0
);
"""


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_index(repo_path: Path, db_path: Path) -> int:
    """Walk the docs content tree, parse all Markdown files, and build the
    SQLite FTS5 database.

    Parameters
    ----------
    repo_path:
        Path to the cloned ``mendix/docs`` repository.
    db_path:
        Output path for the SQLite database file.

    Returns
    -------
    int
        Number of pages indexed.
    """
    content_root = repo_path / "content" / "en" / "docs"
    if not content_root.is_dir():
        raise FileNotFoundError(
            f"Content root not found: {content_root}.  "
            "Make sure the mendix/docs repo is cloned at the given repo_path."
        )

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale DB to force a clean build
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create schema
    conn.executescript(_SCHEMA_SQL)

    # Discover and parse all .md files
    md_files = sorted(content_root.rglob("*.md"))
    logger.info("Found %d Markdown files under %s", len(md_files), content_root)

    docs: list[dict] = []
    for md_file in md_files:
        doc = parse_doc(md_file, content_root)
        if doc is not None:
            docs.append(doc)

    logger.info("Parsed %d documents (skipped %d drafts/errors).", len(docs), len(md_files) - len(docs))

    # Batch insert pages
    conn.executemany(
        """
        INSERT OR REPLACE INTO pages
            (path, title, description, content, version, section,
             breadcrumb, url, last_modified, word_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                d["path"],
                d["title"],
                d["description"],
                d["content"],
                d["version"],
                d["section"],
                d["breadcrumb"],
                d["url"],
                d["last_modified"],
                d["word_count"],
            )
            for d in docs
        ],
    )

    # Rebuild the FTS5 index from the content table
    conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")

    # Build category tree
    _build_categories(conn, docs)

    conn.execute("PRAGMA optimize")
    conn.commit()
    conn.close()

    logger.info("Index built: %d pages -> %s", len(docs), db_path)
    return len(docs)


# ---------------------------------------------------------------------------
# Category tree builder
# ---------------------------------------------------------------------------

def _build_categories(conn: sqlite3.Connection, docs: list[dict]) -> None:
    """Build the category hierarchy from ``_index.md`` pages and directory
    structure information.

    A category is any path that has child pages.  ``_index.md`` files provide
    the title and description; leaf ``.md`` files are pages.
    """
    # Collect all unique directory paths and their metadata
    category_info: dict[str, dict] = {}
    # Count children per path
    children_count: dict[str, int] = {}

    for doc in docs:
        path = doc["path"]
        # Determine parent path
        # e.g. /refguide/microflow/ -> parent is /refguide/
        stripped = path.rstrip("/")
        if "/" not in stripped[1:]:
            # Top-level like /refguide/ — parent is None
            parent = None
        else:
            parent = stripped.rsplit("/", 1)[0] + "/"

        # If this doc comes from an _index.md, it defines a category
        # Heuristic: _index.md pages have paths that match directory paths
        # and will have children.  We record all docs as potential categories.
        category_info[path] = {
            "path": path,
            "title": doc["title"],
            "parent_path": parent,
            "version": doc["version"],
            "description": doc["description"],
            "weight": doc.get("weight", 0),
        }

        # Count this doc as a child of its parent
        if parent:
            children_count[parent] = children_count.get(parent, 0) + 1

    # Insert categories (paths that have children or are known _index.md entries)
    rows = []
    for path, info in category_info.items():
        count = children_count.get(path, 0)
        # Only include as a category if it has children (i.e. it is a section page)
        # or if it is a top-level section
        if count > 0 or info["parent_path"] is None:
            rows.append((
                info["path"],
                info["title"],
                info["parent_path"],
                info["version"],
                info["description"],
                count,
                info["weight"],
            ))

    conn.executemany(
        """
        INSERT OR REPLACE INTO categories
            (path, title, parent_path, version, description, child_count, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    logger.info("Built %d categories.", len(rows))
