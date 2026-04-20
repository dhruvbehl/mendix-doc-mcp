# === Builder stage ===
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir uv

# Copy project metadata and install dependencies
COPY pyproject.toml .
RUN uv pip install --system ".[indexer]"

# Copy application source
COPY src/ src/

# Copy pre-built database (must exist in data/ before building the image)
COPY data/mendix-docs.db data/mendix-docs.db

# === Runtime stage ===
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source and database
COPY --from=builder /app/src src/
COPY --from=builder /app/data/mendix-docs.db data/mendix-docs.db

# Environment
ENV MCP_TRANSPORT=streamable-http
ENV MCP_PORT=8080
ENV MENDIX_DOCS_DB=/app/data/mendix-docs.db

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "src.server", "http"]
