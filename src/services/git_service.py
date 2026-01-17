"""Git operations service for code modifications."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitService:
    """Git operations for self-improvement workflow."""

    def __init__(self, repo_path: Path | str):
        """
        Initialize Git service.

        Args:
            repo_path: Path to the local git repository.
        """
        self.repo_path = Path(repo_path).expanduser().resolve()
        logger.debug("GitService initialized with repo path: %s", self.repo_path)

    async def _run_git_command(self, *args: str) -> tuple[int, str, str]:
        """
        Run git command and return (returncode, stdout, stderr).

        Args:
            *args: Git command arguments (e.g., "status", "--porcelain").

        Returns:
            Tuple of (return_code, stdout, stderr).

        Raises:
            Exception: If subprocess creation fails.
        """
        cmd = ["git", *args]
        logger.debug("Running git command: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            returncode = process.returncode or 0

            if returncode != 0:
                logger.warning(
                    "Git command failed (exit code %d): %s\nstderr: %s",
                    returncode,
                    " ".join(cmd),
                    stderr,
                )
            else:
                logger.debug("Git command succeeded: %s", " ".join(cmd))

            return (returncode, stdout, stderr)

        except Exception as e:
            logger.error("Failed to run git command %s: %s", " ".join(cmd), e)
            raise

    async def ensure_clean_state(self) -> bool:
        """
        Ensure working directory is clean (no uncommitted changes).

        Returns:
            True if working directory is clean, False otherwise.
        """
        logger.debug("Checking git working directory state...")
        returncode, stdout, stderr = await self._run_git_command("status", "--porcelain")

        if returncode != 0:
            logger.error("Failed to check git status: %s", stderr)
            return False

        is_clean = len(stdout.strip()) == 0
        if not is_clean:
            logger.warning("Working directory is not clean:\n%s", stdout)
        else:
            logger.debug("Working directory is clean")

        return is_clean

    async def pull_latest(self, branch: str = "main") -> bool:
        """
        Pull latest changes from remote branch.

        Args:
            branch: Branch to pull from (default: main).

        Returns:
            True if pull succeeded, False otherwise.
        """
        logger.info("Pulling latest changes from origin/%s...", branch)

        # First, checkout the branch
        returncode, stdout, stderr = await self._run_git_command("checkout", branch)
        if returncode != 0:
            logger.error("Failed to checkout %s: %s", branch, stderr)
            return False

        # Then pull
        returncode, stdout, stderr = await self._run_git_command("pull", "origin", branch)
        if returncode != 0:
            logger.error("Failed to pull from origin/%s: %s", branch, stderr)
            return False

        logger.info("Successfully pulled latest changes from origin/%s", branch)
        return True

    async def create_branch(self, branch_name: str, base: str = "main") -> bool:
        """
        Create and checkout new branch from base branch.

        Args:
            branch_name: Name of the new branch to create.
            base: Base branch to branch from (default: main).

        Returns:
            True if branch created successfully, False otherwise.
        """
        logger.info("Creating branch '%s' from origin/%s...", branch_name, base)

        # Create and checkout new branch from remote base
        returncode, stdout, stderr = await self._run_git_command(
            "checkout", "-b", branch_name, f"origin/{base}"
        )

        if returncode != 0:
            logger.error("Failed to create branch %s: %s", branch_name, stderr)
            return False

        logger.info("Successfully created and checked out branch '%s'", branch_name)
        return True

    async def commit_changes(
        self,
        message: str,
        author_name: str = "ATproto Bot",
        author_email: str = "bot@vitorpy.com",
    ) -> bool:
        """
        Stage all changes and commit with message.

        Args:
            message: Commit message.
            author_name: Git author name.
            author_email: Git author email.

        Returns:
            True if commit succeeded, False otherwise.
        """
        logger.info("Staging and committing changes...")

        # Stage all changes
        returncode, stdout, stderr = await self._run_git_command("add", ".")
        if returncode != 0:
            logger.error("Failed to stage changes: %s", stderr)
            return False

        # Commit with author info
        author_string = f"{author_name} <{author_email}>"
        returncode, stdout, stderr = await self._run_git_command(
            "commit", "-m", message, "--author", author_string
        )

        if returncode != 0:
            logger.error("Failed to commit changes: %s", stderr)
            return False

        logger.info("Successfully committed changes")
        logger.debug("Commit message: %s", message)
        return True

    async def push_branch(self, branch_name: str) -> bool:
        """
        Push branch to remote origin.

        Args:
            branch_name: Name of the branch to push.

        Returns:
            True if push succeeded, False otherwise.
        """
        logger.info("Pushing branch '%s' to origin...", branch_name)

        # Push with -u to set upstream
        returncode, stdout, stderr = await self._run_git_command(
            "push", "-u", "origin", branch_name
        )

        if returncode != 0:
            logger.error("Failed to push branch %s: %s", branch_name, stderr)
            return False

        logger.info("Successfully pushed branch '%s' to origin", branch_name)
        return True

    async def get_diff(self, base: str = "main") -> str:
        """
        Get diff against base branch.

        Args:
            base: Base branch to diff against.

        Returns:
            Diff output as string, or empty string on error.
        """
        logger.debug("Getting diff against %s...", base)

        returncode, stdout, stderr = await self._run_git_command("diff", f"{base}...HEAD")

        if returncode != 0:
            logger.error("Failed to get diff: %s", stderr)
            return ""

        return stdout

    async def get_current_branch(self) -> Optional[str]:
        """
        Get current branch name.

        Returns:
            Current branch name, or None on error.
        """
        returncode, stdout, stderr = await self._run_git_command(
            "rev-parse", "--abbrev-ref", "HEAD"
        )

        if returncode != 0:
            logger.error("Failed to get current branch: %s", stderr)
            return None

        return stdout.strip()
