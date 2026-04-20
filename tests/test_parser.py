"""Tests for the Mendix documentation parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.indexer.parser import (
    SHORTCODE_PATTERN,
    SNIPPET_PATTERN,
    VERSION_MAP,
    _convert_relative_links,
    parse_doc,
)


# ---------------------------------------------------------------------------
# Tests: Hugo shortcode stripping
# ---------------------------------------------------------------------------

class TestShortcodeStripping:
    def test_figure_shortcode(self):
        text = '{{< figure src="attachments/microflow/example.png" >}}'
        result = SHORTCODE_PATTERN.sub("", text)
        assert result.strip() == ""

    def test_alert_paired_shortcode_keeps_inner_text(self):
        text = '{{% alert color="info" %}}This is important.{{% /alert %}}'
        result = SHORTCODE_PATTERN.sub("", text)
        assert result.strip() == "This is important."

    def test_youtube_shortcode(self):
        text = '{{< youtube id="abc123" >}}'
        result = SHORTCODE_PATTERN.sub("", text)
        assert result.strip() == ""

    def test_icon_shortcode(self):
        text = '{{< icon name="pencil" >}}'
        result = SHORTCODE_PATTERN.sub("", text)
        assert result.strip() == ""

    def test_snippet_pattern_replaced(self):
        text = '{{% snippet file="refguide/common.md" %}}'
        result = SNIPPET_PATTERN.sub("[snippet omitted]", text)
        assert result == "[snippet omitted]"

    def test_mixed_content_preserves_markdown(self):
        text = textwrap.dedent("""\
            ## Introduction

            {{< figure src="img.png" >}}

            This is regular **Markdown** content.

            {{% alert color="warning" %}}Watch out!{{% /alert %}}

            More content here.
        """)
        result = SHORTCODE_PATTERN.sub("", text)
        assert "## Introduction" in result
        assert "regular **Markdown** content" in result
        assert "Watch out!" in result
        assert "More content here." in result
        assert "{{" not in result


# ---------------------------------------------------------------------------
# Tests: Version detection
# ---------------------------------------------------------------------------

class TestVersionDetection:
    def test_refguide_is_v11(self):
        assert VERSION_MAP["refguide"] == "11"

    def test_refguide10_is_v10(self):
        assert VERSION_MAP["refguide10"] == "10"

    def test_howto9_is_v9(self):
        assert VERSION_MAP["howto9"] == "9"

    def test_howto8_is_v8(self):
        assert VERSION_MAP["howto8"] == "8"

    def test_unknown_section_is_all(self):
        assert VERSION_MAP.get("deployment", "all") == "all"
        assert VERSION_MAP.get("apidocs-mxsdk", "all") == "all"


# ---------------------------------------------------------------------------
# Tests: Relative link conversion
# ---------------------------------------------------------------------------

class TestRelativeLinkConversion:
    def test_sibling_link(self):
        body = "[See microflow](../microflow/)"
        result = _convert_relative_links(body, "/refguide/nanoflow/")
        assert "https://docs.mendix.com/refguide/microflow/" in result

    def test_absolute_link_preserved(self):
        body = "[Google](https://google.com)"
        result = _convert_relative_links(body, "/refguide/microflow/")
        assert result == body

    def test_anchor_link_preserved(self):
        body = "[Section](#details)"
        result = _convert_relative_links(body, "/refguide/microflow/")
        assert result == body

    def test_root_relative_link(self):
        body = "[Deployment](/deployment/mendix-cloud/)"
        result = _convert_relative_links(body, "/refguide/microflow/")
        assert "https://docs.mendix.com/deployment/mendix-cloud/" in result


# ---------------------------------------------------------------------------
# Tests: Full document parsing
# ---------------------------------------------------------------------------

class TestParseDocs:
    @pytest.fixture()
    def content_root(self, tmp_path: Path) -> Path:
        """Create a minimal content directory with test Markdown files."""
        root = tmp_path / "content" / "en" / "docs"

        # Create refguide section
        refguide = root / "refguide"
        refguide.mkdir(parents=True)

        # _index.md for refguide
        (refguide / "_index.md").write_text(textwrap.dedent("""\
            ---
            title: "Studio Pro 11 Guide"
            description: "Reference guide for Studio Pro 11"
            weight: 10
            ---
            Welcome to the Studio Pro 11 reference guide.
        """))

        # Regular page
        (refguide / "microflow.md").write_text(textwrap.dedent("""\
            ---
            title: "Microflows"
            description: "How to build microflows"
            weight: 20
            tags: ["microflow", "logic"]
            ---
            A microflow is a visual way to express logic.

            {{< figure src="attachments/microflow.png" >}}

            See [nanoflows](../nanoflow/) for more.
        """))

        # Draft page — should be skipped
        (refguide / "draft-page.md").write_text(textwrap.dedent("""\
            ---
            title: "Draft Feature"
            draft: true
            ---
            This should not be indexed.
        """))

        return root

    def test_parse_regular_page(self, content_root: Path):
        doc = parse_doc(content_root / "refguide" / "microflow.md", content_root)
        assert doc is not None
        assert doc["title"] == "Microflows"
        assert doc["version"] == "11"
        assert doc["section"] == "refguide"
        assert doc["path"] == "/refguide/microflow/"
        assert doc["url"] == "https://docs.mendix.com/refguide/microflow/"
        # Shortcodes should be stripped
        assert "{{" not in doc["content"]
        # Relative links should be converted
        assert "https://docs.mendix.com" in doc["content"]

    def test_parse_index_page(self, content_root: Path):
        doc = parse_doc(content_root / "refguide" / "_index.md", content_root)
        assert doc is not None
        assert doc["title"] == "Studio Pro 11 Guide"
        assert doc["path"] == "/refguide/"

    def test_skip_draft(self, content_root: Path):
        doc = parse_doc(content_root / "refguide" / "draft-page.md", content_root)
        assert doc is None

    def test_front_matter_extraction(self, content_root: Path):
        doc = parse_doc(content_root / "refguide" / "microflow.md", content_root)
        assert doc["description"] == "How to build microflows"
        assert doc["tags"] == ["microflow", "logic"]
        assert doc["weight"] == 20
