"""Markdown + front-matter + Hugo shortcode parser for Mendix documentation."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hugo shortcode patterns
# ---------------------------------------------------------------------------

# Matches both {{< ... >}} and {{% ... %}} forms, including self-closing and
# closing tags like {{% /alert %}}.  We intentionally match only the *tags*
# (not the content between paired tags) so inner text is preserved.
SHORTCODE_PATTERN = re.compile(
    r"\{\{[<%]\s*/?\s*[\w-]+(?:\s[^}]*)?\s*[%>]\}\}"
)

# Snippet include shortcodes — we cannot resolve these at index time so we
# replace them with a placeholder.
SNIPPET_PATTERN = re.compile(
    r"\{\{[<%]\s*snippet\s+file=[\"'][^\"']+[\"']\s*[%>]\}\}"
)

# ---------------------------------------------------------------------------
# Version mapping (ADR-004)
# ---------------------------------------------------------------------------

VERSION_MAP: dict[str, str] = {
    "refguide": "11",
    "howto": "11",
    "refguide10": "10",
    "howto10": "10",
    "refguide9": "9",
    "howto9": "9",
    "refguide8": "8",
    "howto8": "8",
}

# ---------------------------------------------------------------------------
# Relative link conversion
# ---------------------------------------------------------------------------

_RELATIVE_LINK = re.compile(
    r"\[([^\]]*)\]\((?!https?://)(?!#)(?!mailto:)([^)]+)\)"
)

BASE_URL = "https://docs.mendix.com"


def _convert_relative_links(body: str, page_url_path: str) -> str:
    """Convert relative Markdown links to absolute docs.mendix.com URLs."""
    import posixpath

    def _replace(match: re.Match) -> str:
        text = match.group(1)
        href = match.group(2)
        # Resolve ../ and ./ relative to the page's directory
        if href.startswith("/"):
            absolute = href
        else:
            # page_url_path is like /refguide/nanoflow/
            # The "directory" of this page is itself (it ends with /)
            base_dir = page_url_path if page_url_path.endswith("/") else posixpath.dirname(page_url_path) + "/"
            absolute = posixpath.normpath(base_dir + href)
            # normpath strips trailing slash; re-add if the original href had one
            # or if the path looks like a directory (no file extension)
            if not posixpath.splitext(absolute)[1]:
                absolute = absolute.rstrip("/") + "/"
        # Ensure leading slash
        if not absolute.startswith("/"):
            absolute = "/" + absolute
        # Ensure trailing slash for consistency (unless it has an anchor/query)
        if "#" not in absolute and "?" not in absolute and not absolute.endswith("/"):
            absolute += "/"
        return f"[{text}]({BASE_URL}{absolute})"

    return _RELATIVE_LINK.sub(_replace, body)


# ---------------------------------------------------------------------------
# Breadcrumb builder
# ---------------------------------------------------------------------------

def _build_breadcrumb(rel_path: Path, content_root: Path) -> str:
    """Build a breadcrumb string from the file's position in the doc tree.

    Walks *up* from the file, collecting titles from ``_index.md`` files in
    each parent directory.  Falls back to the directory name when no
    ``_index.md`` is found.
    """
    parts: list[str] = []
    current = rel_path.parent
    while current != Path("."):
        index_file = content_root / current / "_index.md"
        if index_file.exists():
            try:
                post = frontmatter.load(str(index_file))
                parts.append(post.get("title", current.name))
            except Exception:
                parts.append(current.name)
        else:
            parts.append(current.name)
        current = current.parent
    parts.reverse()
    return " > ".join(parts)


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_doc(file_path: Path, content_root: Path) -> dict | None:
    """Parse a single Mendix documentation Markdown file.

    Parameters
    ----------
    file_path:
        Absolute path to the ``.md`` file.
    content_root:
        Absolute path to the ``content/en/docs`` directory in the repo.

    Returns
    -------
    dict | None
        Parsed document dict ready for insertion, or ``None`` if the file
        should be skipped (e.g. drafts).
    """
    try:
        post = frontmatter.load(str(file_path))
    except Exception:
        logger.warning("Failed to parse front matter: %s", file_path)
        return None

    # Skip drafts
    if post.get("draft", False):
        return None

    rel_path = file_path.relative_to(content_root)
    section = rel_path.parts[0] if rel_path.parts else ""
    version = VERSION_MAP.get(section, "all")

    # Build URL path: prefer explicit `url` front matter (all Mendix docs have
    # this), fall back to deriving from the file path.
    url_path = post.get("url", "") or ""
    if not url_path:
        url_path = str(rel_path)
        if url_path.endswith("_index.md"):
            url_path = url_path[: -len("_index.md")]
        elif url_path.endswith(".md"):
            url_path = url_path[: -len(".md")] + "/"
    url_path = "/" + url_path.strip("/") + "/"
    if url_path == "//":
        url_path = "/"

    # Clean content — strip shortcodes
    body = post.content
    body = SNIPPET_PATTERN.sub("[snippet omitted]", body)
    body = SHORTCODE_PATTERN.sub("", body)
    body = _convert_relative_links(body, url_path)

    # Extract front-matter fields
    title = post.get("title", rel_path.stem)
    description = post.get("description", "") or ""
    last_modified = post.get("lastmod", "") or post.get("last_modified", "") or ""
    if last_modified and not isinstance(last_modified, str):
        last_modified = str(last_modified)
    weight = post.get("weight", 0) or 0
    tags = post.get("tags", []) or []

    breadcrumb = _build_breadcrumb(rel_path, content_root)

    return {
        "path": url_path,
        "title": title,
        "description": description,
        "content": body,
        "version": version,
        "section": section,
        "url": f"{BASE_URL}{url_path}",
        "breadcrumb": breadcrumb,
        "last_modified": last_modified,
        "weight": weight,
        "tags": tags,
        "word_count": len(body.split()),
    }
