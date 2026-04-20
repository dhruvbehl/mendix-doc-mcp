# Mendix Documentation MCP Server

An MCP (Model Context Protocol) server that indexes and serves the official [Mendix documentation](https://docs.mendix.com) for use with AI coding assistants like Claude Code, Cursor, and VS Code Copilot.

It provides version-aware full-text search over 3,000-5,000+ documentation pages covering Studio Pro versions 8 through 11, powered by SQLite FTS5 with BM25 ranking.

## Features

- **3 focused tools** following MCP best practices: search, retrieve, and browse
- **Version-aware search** scoped to Studio Pro 8, 9, 10, or 11
- **Sub-100ms search latency** via SQLite FTS5 with BM25 ranking
- **Dual transport** support: stdio (local) and Streamable HTTP (remote)
- **Zero external dependencies** at runtime -- single SQLite file, no database server needed

## Quick Start (Local / stdio)

### 1. Install

```bash
pip install mendix-doc-mcp
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uvx mendix-doc-mcp
```

### 2. Build the index

Clone the Mendix docs repo and build the search database:

```bash
pip install mendix-doc-mcp[indexer]
python scripts/index.py --repo-path ./mendix-docs-repo --output ./data/mendix-docs.db
```

### 3. Configure your MCP client

**Claude Code** (`~/.claude.json`):

```json
{
  "mcpServers": {
    "mendix-docs": {
      "command": "python",
      "args": ["-m", "src.server"],
      "env": {
        "MENDIX_DOCS_DB": "/path/to/data/mendix-docs.db"
      }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mendix-docs": {
      "command": "python",
      "args": ["-m", "src.server", "stdio"],
      "env": {
        "MENDIX_DOCS_DB": "/path/to/data/mendix-docs.db"
      }
    }
  }
}
```

## Quick Start (Remote / HTTP)

Start the server with Streamable HTTP transport:

```bash
python scripts/serve.py --transport http --db ./data/mendix-docs.db --port 8080
```

Then configure your MCP client to connect to `http://your-host:8080/mcp`.

## Tools

### `search_mendix_docs`

Search Mendix documentation by keyword. Returns ranked results with snippets.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | (required) | Search keywords or phrase |
| `version` | string | `"11"` | Studio Pro version: "8", "9", "10", "11" |
| `max_results` | int | `5` | Max results (1-20) |

### `get_mendix_doc`

Retrieve the full Markdown content of a specific documentation page.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | (required) | Doc path or full URL |
| `version` | string | `"11"` | Version hint |

### `list_mendix_doc_categories`

Browse the documentation hierarchy to discover available content.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `version` | string | `"11"` | Studio Pro version |

## Building the Index

The indexer clones the [mendix/docs](https://github.com/mendix/docs) repository and builds a SQLite FTS5 database:

```bash
# Full build (clone + index)
python scripts/index.py --repo-path ./mendix-docs-repo --output ./data/mendix-docs.db

# Skip clone (use existing repo checkout)
python scripts/index.py --repo-path ./mendix-docs-repo --output ./data/mendix-docs.db --skip-clone
```

## Deploying to AWS

The server is designed to run on ECS/Fargate with the SQLite database baked into the container image.

### 1. Build the index locally

```bash
python scripts/index.py --output ./data/mendix-docs.db
```

### 2. Build and push the Docker image

```bash
docker build -f deploy/Dockerfile -t mendix-doc-mcp .
docker tag mendix-doc-mcp:latest <account>.dkr.ecr.eu-central-1.amazonaws.com/mendix-doc-mcp:latest
docker push <account>.dkr.ecr.eu-central-1.amazonaws.com/mendix-doc-mcp:latest
```

### 3. Deploy to ECS

Use the task definition in `deploy/task-definition.json` (update the image URI first):

```bash
aws ecs register-task-definition --cli-input-json file://deploy/task-definition.json
aws ecs update-service --cluster mendix-doc-mcp --service mendix-doc-mcp --force-new-deployment
```

The ALB should be configured with an idle timeout of 300 seconds to support Streamable HTTP connections.

## Development

```bash
# Install dev dependencies
pip install -e ".[indexer,dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

## License

MIT. The indexed content from the Mendix documentation is licensed under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) by Mendix.
