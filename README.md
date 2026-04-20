# Mendix Documentation MCP Server

MCP server that provides full-text search over 4,000+ [Mendix documentation](https://docs.mendix.com) pages. Works with Claude Code, Cursor, VS Code, and any MCP-compatible client.

Version-aware search across Studio Pro 8–11, powered by SQLite FTS5 with BM25 ranking. Auto-builds the index on first run — no setup required.

## Quick Start

Add to your MCP client config:

**Claude Code** (`~/.claude.json`):

```json
{
  "mcpServers": {
    "mendix-docs": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mendix-doc-mcp"]
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mendix-docs": {
      "command": "uvx",
      "args": ["mendix-doc-mcp"]
    }
  }
}
```

**Cursor / VS Code** (MCP settings):

```json
{
  "mendix-docs": {
    "command": "uvx",
    "args": ["mendix-doc-mcp"]
  }
}
```

First run clones the [mendix/docs](https://github.com/mendix/docs) repo and builds the search index (~70 seconds). Subsequent runs start instantly.

## Tools

### `search_mendix_docs`

Search documentation by keyword. Returns ranked results with snippets.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search keywords |
| `version` | string | `"11"` | Studio Pro version: `"8"`, `"9"`, `"10"`, `"11"` |
| `max_results` | int | `5` | Max results (1–20) |

### `get_mendix_doc`

Retrieve full Markdown content of a specific page.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | required | Doc path or full docs.mendix.com URL |

### `list_mendix_doc_categories`

Browse documentation hierarchy.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `version` | string | `"11"` | Studio Pro version |

## How It Works

1. Clones [mendix/docs](https://github.com/mendix/docs) (shallow, ~500MB)
2. Parses 4,000+ Markdown files with Hugo front matter
3. Builds SQLite FTS5 index with BM25 ranking
4. Serves via MCP (stdio or Streamable HTTP)

Index and repo are cached locally:
- macOS: `~/Library/Caches/mendix-doc-mcp/`
- Linux: `~/.cache/mendix-doc-mcp/`

To refresh the index, delete the cache directory and restart.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT. Mendix documentation content is [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) by Mendix.
