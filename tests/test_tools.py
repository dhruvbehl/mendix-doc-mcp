"""Tests for MCP tool registration and basic behavior."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    """Create a minimal test database for tools testing."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            content TEXT NOT NULL,
            version TEXT NOT NULL,
            section TEXT NOT NULL,
            breadcrumb TEXT,
            url TEXT NOT NULL,
            last_modified TEXT,
            word_count INTEGER
        );

        CREATE VIRTUAL TABLE pages_fts USING fts5(
            title, description, content,
            content='pages', content_rowid='id',
            tokenize='porter unicode61'
        );

        CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, title, description, content)
            VALUES (new.id, new.title, new.description, new.content);
        END;

        CREATE TABLE categories (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            parent_path TEXT,
            version TEXT NOT NULL,
            description TEXT,
            child_count INTEGER DEFAULT 0,
            weight INTEGER DEFAULT 0
        );

        INSERT INTO pages (path, title, description, content, version, section, breadcrumb, url, last_modified, word_count)
        VALUES ('/refguide/microflow/', 'Microflows', 'Build microflows', 'A microflow is visual logic.', '11', 'refguide',
                'Studio Pro 11 > Microflow', 'https://docs.mendix.com/refguide/microflow/', '2026-01-01', 5);

        INSERT INTO categories (path, title, parent_path, version, description, child_count, weight)
        VALUES ('/refguide/', 'Studio Pro 11 Guide', NULL, '11', 'Reference guide', 1, 10);
    """)
    conn.commit()
    conn.close()
    return db_file


# ---------------------------------------------------------------------------
# Tests: Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_mcp_instance_exists(self):
        from src.server.tools import mcp
        assert mcp is not None
        assert mcp.name == "mendix-docs"

    def test_tools_are_registered(self):
        from src.server.tools import mcp
        # FastMCP exposes registered tools via list_tools()
        # We check that our 3 tool functions are importable
        from src.server.tools import (
            get_mendix_doc,
            list_mendix_doc_categories,
            search_mendix_docs,
        )
        assert callable(search_mendix_docs)
        assert callable(get_mendix_doc)
        assert callable(list_mendix_doc_categories)


# ---------------------------------------------------------------------------
# Tests: Tool behavior with test DB
# ---------------------------------------------------------------------------

class TestToolBehavior:
    @pytest.fixture(autouse=True)
    def _setup_db(self, test_db: Path):
        """Patch the engine cache to use the test database."""
        from src.search.engine import SearchEngine

        engine = SearchEngine(test_db)
        with patch("src.server.tools._get_engine", return_value=engine):
            yield
        engine.close()

    def test_search_returns_results(self):
        from src.server.tools import search_mendix_docs
        results = search_mendix_docs("microflow")
        assert isinstance(results, list)
        assert len(results) >= 1
        assert results[0]["title"] == "Microflows"

    def test_search_empty_query(self):
        from src.server.tools import search_mendix_docs
        results = search_mendix_docs("")
        assert results == []

    def test_get_doc_found(self):
        from src.server.tools import get_mendix_doc
        result = get_mendix_doc("/refguide/microflow/")
        assert "error" not in result
        assert result["title"] == "Microflows"

    def test_get_doc_not_found(self):
        from src.server.tools import get_mendix_doc
        result = get_mendix_doc("/nonexistent/")
        assert "error" in result

    def test_list_categories(self):
        from src.server.tools import list_mendix_doc_categories
        result = list_mendix_doc_categories(version="11")
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["title"] == "Studio Pro 11 Guide"
