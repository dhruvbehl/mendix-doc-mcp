"""Tests for the search engine (FTS5 queries, BM25 ranking, version filtering)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.search.engine import SearchEngine, _sanitize_fts5_query


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a minimal FTS5 database with test data."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))

    conn.executescript("""
        CREATE TABLE pages (
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

        CREATE VIRTUAL TABLE pages_fts USING fts5(
            title,
            description,
            content,
            content='pages',
            content_rowid='id',
            tokenize='porter unicode61'
        );

        CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, title, description, content)
            VALUES (new.id, new.title, new.description, new.content);
        END;

        CREATE TABLE categories (
            path        TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            parent_path TEXT,
            version     TEXT NOT NULL,
            description TEXT,
            child_count INTEGER DEFAULT 0,
            weight      INTEGER DEFAULT 0
        );
    """)

    # Insert test pages
    conn.executemany(
        """INSERT INTO pages
            (path, title, description, content, version, section, breadcrumb, url, last_modified, word_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                "/refguide/microflow/",
                "Microflows",
                "How to build microflows in Studio Pro",
                "A microflow is a visual way to express logic in your Mendix application. "
                "Microflows can be used to perform actions such as creating and changing objects, "
                "showing pages, and making choices.",
                "11",
                "refguide",
                "Studio Pro 11 > App Modeling > Microflow",
                "https://docs.mendix.com/refguide/microflow/",
                "2026-01-15",
                35,
            ),
            (
                "/refguide10/microflow/",
                "Microflows",
                "How to build microflows in Studio Pro 10",
                "A microflow is a visual way to express logic in your Mendix application.",
                "10",
                "refguide10",
                "Studio Pro 10 > App Modeling > Microflow",
                "https://docs.mendix.com/refguide10/microflow/",
                "2025-06-01",
                14,
            ),
            (
                "/refguide/rest-call-action/",
                "Call REST Service",
                "Configure a REST call in a microflow",
                "Use the Call REST service action to call a REST endpoint from a microflow. "
                "You can configure the HTTP method, URL, headers, and request body.",
                "11",
                "refguide",
                "Studio Pro 11 > Integration > REST",
                "https://docs.mendix.com/refguide/rest-call-action/",
                "2026-02-10",
                30,
            ),
            (
                "/deployment/mendix-cloud/",
                "Mendix Cloud",
                "Deploy your app to Mendix Cloud",
                "Mendix Cloud is the default deployment option for Mendix applications. "
                "It provides a fully managed environment.",
                "all",
                "deployment",
                "Deployment > Mendix Cloud",
                "https://docs.mendix.com/deployment/mendix-cloud/",
                "2026-03-01",
                20,
            ),
        ],
    )

    # Insert test categories
    conn.executemany(
        """INSERT INTO categories (path, title, parent_path, version, description, child_count, weight)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("/refguide/", "Studio Pro 11 Guide", None, "11", "Reference guide for Studio Pro 11", 2, 10),
            ("/refguide10/", "Studio Pro 10 Guide", None, "10", "Reference guide for Studio Pro 10", 1, 20),
            ("/deployment/", "Deployment", None, "all", "Deployment guides", 1, 30),
        ],
    )

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture()
def engine(db_path: Path) -> SearchEngine:
    eng = SearchEngine(db_path)
    yield eng
    eng.close()


# ---------------------------------------------------------------------------
# Tests: FTS5 query sanitisation
# ---------------------------------------------------------------------------

class TestSanitizeFts5Query:
    def test_simple_terms(self):
        assert _sanitize_fts5_query("microflow") == "microflow*"

    def test_multiple_terms(self):
        assert _sanitize_fts5_query("REST call action") == "REST* call* action*"

    def test_special_characters_stripped(self):
        result = _sanitize_fts5_query('query: with "special" chars*')
        # Colons, quotes, asterisks should be stripped
        assert ":" not in result
        assert '"' not in result.replace('""', "")

    def test_empty_query(self):
        assert _sanitize_fts5_query("") == '""'

    def test_only_special_chars(self):
        assert _sanitize_fts5_query(":::**") == '""'


# ---------------------------------------------------------------------------
# Tests: Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_basic_search(self, engine: SearchEngine):
        results = engine.search("microflow")
        assert len(results) >= 1
        assert results[0].title == "Microflows"

    def test_version_filter_v11(self, engine: SearchEngine):
        results = engine.search("microflow", version="11")
        versions = {r.version for r in results}
        # Should only get v11 and 'all' pages
        assert versions <= {"11", "all"}

    def test_version_filter_v10(self, engine: SearchEngine):
        results = engine.search("microflow", version="10")
        versions = {r.version for r in results}
        assert versions <= {"10", "all"}

    def test_version_all_included(self, engine: SearchEngine):
        """Pages with version='all' should appear regardless of version filter."""
        results = engine.search("deployment", version="11")
        assert any(r.version == "all" for r in results)

    def test_limit_respected(self, engine: SearchEngine):
        results = engine.search("microflow", limit=1)
        assert len(results) <= 1

    def test_limit_capped_at_20(self, engine: SearchEngine):
        # Even if we ask for 100, the engine caps at 20
        results = engine.search("microflow", limit=100)
        assert len(results) <= 20

    def test_bm25_title_boost(self, engine: SearchEngine):
        """A page with the query term in the title should rank higher."""
        results = engine.search("microflow", version="11")
        # "Microflows" should rank above "Call REST Service" (which mentions
        # microflow only in the body)
        if len(results) >= 2:
            titles = [r.title for r in results]
            assert titles.index("Microflows") < titles.index("Call REST Service")

    def test_empty_query_returns_nothing(self, engine: SearchEngine):
        results = engine.search("")
        assert results == []

    def test_snippet_present(self, engine: SearchEngine):
        results = engine.search("microflow")
        assert results[0].snippet  # should be non-empty


# ---------------------------------------------------------------------------
# Tests: Get page
# ---------------------------------------------------------------------------

class TestGetPage:
    def test_get_existing_page(self, engine: SearchEngine):
        page = engine.get_page("/refguide/microflow/")
        assert page is not None
        assert page.title == "Microflows"
        assert "microflow" in page.content.lower()

    def test_get_page_not_found(self, engine: SearchEngine):
        page = engine.get_page("/nonexistent/page/")
        assert page is None

    def test_get_page_by_url(self, engine: SearchEngine):
        page = engine.get_page("https://docs.mendix.com/refguide/microflow/")
        assert page is not None
        assert page.title == "Microflows"

    def test_path_normalisation_no_trailing_slash(self, engine: SearchEngine):
        page = engine.get_page("/refguide/microflow")
        assert page is not None

    def test_path_normalisation_no_leading_slash(self, engine: SearchEngine):
        page = engine.get_page("refguide/microflow/")
        assert page is not None


# ---------------------------------------------------------------------------
# Tests: List categories
# ---------------------------------------------------------------------------

class TestListCategories:
    def test_root_categories(self, engine: SearchEngine):
        cats = engine.list_categories("/", version="11")
        paths = {c.path for c in cats}
        assert "/refguide/" in paths
        # deployment is version='all', so should appear for v11
        assert "/deployment/" in paths

    def test_version_filtering(self, engine: SearchEngine):
        cats = engine.list_categories("/", version="10")
        paths = {c.path for c in cats}
        assert "/refguide10/" in paths
        # v11-only refguide should NOT appear for v10
        assert "/refguide/" not in paths

    def test_category_has_child_count(self, engine: SearchEngine):
        cats = engine.list_categories("/", version="11")
        refguide = next(c for c in cats if c.path == "/refguide/")
        assert refguide.child_count == 2
        assert refguide.type == "category"
