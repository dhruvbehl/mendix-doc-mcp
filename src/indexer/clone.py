"""Git clone and incremental pull for the mendix/docs repository."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/mendix/docs.git"
REPO_BRANCH = "development"
CONTENT_ROOT = "content/en/docs"


def sync_repo(repo_path: Path) -> list[str]:
    """Clone the mendix/docs repo (or pull if it already exists).

    Parameters
    ----------
    repo_path:
        Local filesystem path where the repo should live.

    Returns
    -------
    list[str]
        List of changed ``.md`` file paths relative to the repo root.
        Empty on first clone (indicates a full rebuild is needed) or when
        there are no new changes.
    """
    # Import here so that gitpython is only needed when running the indexer
    try:
        from git import Repo
    except ImportError as exc:
        raise ImportError(
            "gitpython is required for the indexer. "
            "Install it with: pip install mendix-doc-mcp[indexer]"
        ) from exc

    repo_path = Path(repo_path)

    if not (repo_path / ".git").exists():
        logger.info("Cloning %s (branch=%s, depth=1) into %s", REPO_URL, REPO_BRANCH, repo_path)
        Repo.clone_from(
            REPO_URL,
            str(repo_path),
            branch=REPO_BRANCH,
            depth=1,
        )
        logger.info("Clone complete.")
        return []  # full rebuild needed

    logger.info("Repository exists at %s — pulling latest changes.", repo_path)
    repo = Repo(str(repo_path))
    old_head = repo.head.commit.hexsha

    # Shallow repos need fetch + reset instead of pull
    origin = repo.remotes.origin
    origin.fetch(depth=1)

    remote_head = origin.refs[REPO_BRANCH].commit.hexsha
    if old_head == remote_head:
        logger.info("Already up to date (HEAD=%s).", old_head[:12])
        return []

    # Reset to fetched HEAD (works with shallow clones)
    repo.head.reset(remote_head, index=True, working_tree=True)
    logger.info("Updated %s -> %s", old_head[:12], remote_head[:12])

    # Determine which Markdown files under CONTENT_ROOT changed
    diff_output = repo.git.diff(
        "--name-only",
        old_head,
        remote_head,
        "--",
        CONTENT_ROOT,
    )
    changed = [f for f in diff_output.splitlines() if f.endswith(".md")]
    logger.info("Changed files: %d", len(changed))
    return changed
