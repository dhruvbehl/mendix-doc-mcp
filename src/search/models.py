"""Pydantic models for the Mendix Documentation MCP Server."""

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search result from the FTS5 index."""

    title: str = Field(description="Page title")
    path: str = Field(description="Document path, e.g. '/refguide/microflow/'")
    url: str = Field(description="Full docs.mendix.com URL")
    section: str = Field(description="Top-level section, e.g. 'refguide', 'howto'")
    version: str = Field(description="Studio Pro version: '8', '9', '10', '11', or 'all'")
    snippet: str = Field(description="Relevant text excerpt with matched terms highlighted")
    score: float = Field(description="BM25 relevance score (more negative = more relevant)")


class DocPage(BaseModel):
    """Full content of a single documentation page."""

    title: str = Field(description="Page title")
    content: str = Field(description="Full page content as clean Markdown")
    url: str = Field(description="Canonical docs.mendix.com URL")
    version: str = Field(description="Studio Pro version this page belongs to")
    breadcrumb: str = Field(default="", description="Navigation path, e.g. 'Studio Pro 11 > Microflow'")
    last_modified: str = Field(default="", description="Last modification date")


class Category(BaseModel):
    """A documentation category or page entry in the hierarchy."""

    title: str = Field(description="Category or page title")
    path: str = Field(description="Path for use with get_mendix_doc or list_mendix_doc_categories")
    type: str = Field(description="'category' (has children) or 'page' (leaf document)")
    description: str = Field(default="", description="Short description from front matter")
    child_count: int = Field(default=0, description="Number of child pages (for categories)")
