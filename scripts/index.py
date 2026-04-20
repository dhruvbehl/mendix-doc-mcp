#!/usr/bin/env python3
"""CLI script to build the Mendix documentation search index.

Usage:
    python scripts/index.py --repo-path ./mendix-docs-repo --output ./data/mendix-docs.db
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.indexer.builder import build_index
from src.indexer.clone import sync_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--repo-path",
    type=click.Path(path_type=Path),
    default=Path("./mendix-docs-repo"),
    help="Path to clone (or find) the mendix/docs repository.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("./data/mendix-docs.db"),
    help="Output path for the SQLite database.",
)
@click.option(
    "--skip-clone",
    is_flag=True,
    default=False,
    help="Skip the git clone/pull step (use existing repo as-is).",
)
def main(repo_path: Path, output: Path, skip_clone: bool) -> None:
    """Build the Mendix documentation FTS5 search index."""
    repo_path = repo_path.resolve()
    output = output.resolve()

    if not skip_clone:
        logger.info("Syncing repository to %s ...", repo_path)
        changed = sync_repo(repo_path)
        if changed:
            logger.info("Changed files since last pull: %d", len(changed))
        else:
            logger.info("Full rebuild (first clone or no changes detected).")

    logger.info("Building index -> %s ...", output)
    count = build_index(repo_path, output)
    logger.info("Done. Indexed %d pages.", count)


if __name__ == "__main__":
    main()
