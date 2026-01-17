"""Self-improvement orchestration service."""

import logging
import time
from typing import Any

from ..config import Config
from .code_analysis_service import CodeAnalysisService
from .git_service import GitService
from .github_service import GitHubService

logger = logging.getLogger(__name__)


class SelfImprovementService:
    """Orchestrate self-improvement workflow."""

    def __init__(
        self,
        git_service: GitService,
        github_service: GitHubService,
        code_analysis_service: CodeAnalysisService,
        config: Config,
    ):
        """
        Initialize self-improvement service.

        Args:
            git_service: Git operations service.
            github_service: GitHub API service.
            code_analysis_service: Code analysis service.
            config: Bot configuration.
        """
        self.git = git_service
        self.github = github_service
        self.code_analysis = code_analysis_service
        self.config = config
        logger.debug("SelfImprovementService initialized")

    async def execute_selfimprovement(
        self, prompt: str, requester_did: str, conversation_id: str
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Execute full self-improvement workflow.

        Args:
            prompt: User's improvement request.
            requester_did: DID of the requester.
            conversation_id: Conversation/thread ID.

        Returns:
            Tuple of (success, message, metadata) where:
                - success: True if PR created, False otherwise
                - message: PR URL or error message
                - metadata: Dict with branch_name, pr_number, pr_url, execution_time_ms, error
        """
        start_time = time.time()
        metadata: dict[str, Any] = {
            "branch_name": None,
            "pr_number": None,
            "pr_url": None,
            "execution_time_ms": None,
            "error": None,
        }

        try:
            # 1. Verify requester is owner
            if requester_did != self.config.bluesky.owner_did:
                error_msg = "Unauthorized: Only bot owner can use /selfimprovement"
                logger.warning("Unauthorized self-improvement request from %s", requester_did)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 2. Verify GitHub configured
            if not self.config.github:
                error_msg = "GitHub not configured. Please configure GitHub App credentials."
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 3. Pull latest code
            logger.info("Step 1/10: Pulling latest code from main...")
            success = await self.git.pull_latest("main")
            if not success:
                error_msg = "Failed to pull latest code from main branch"
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 4. Ensure clean state
            logger.info("Step 2/10: Checking working directory is clean...")
            if not await self.git.ensure_clean_state():
                error_msg = "Working directory is not clean. Please commit or stash changes."
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 5. Generate changes with Claude
            logger.info("Step 3/10: Analyzing prompt and generating code changes...")
            changes_result = await self.code_analysis.analyze_and_generate_changes(
                prompt, conversation_id
            )

            if not changes_result["success"]:
                error_msg = f"Failed to generate valid changes: {changes_result['explanation']}"
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            if not changes_result["changes"]:
                error_msg = "No changes generated. The request may be unclear or unnecessary."
                logger.warning(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 6. Create branch
            branch_name = changes_result["branch_name"]
            metadata["branch_name"] = branch_name

            logger.info("Step 4/10: Creating branch '%s'...", branch_name)
            if not await self.git.create_branch(branch_name):
                error_msg = f"Failed to create branch '{branch_name}'"
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 7. Apply changes to filesystem
            logger.info("Step 5/10: Applying %d file changes...", len(changes_result["changes"]))
            success, error = await self.code_analysis.apply_changes(changes_result["changes"])
            if not success:
                error_msg = f"Failed to apply changes: {error}"
                logger.error(error_msg)
                metadata["error"] = error_msg
                # Try to cleanup: go back to main
                await self.git.pull_latest("main")
                return (False, error_msg, metadata)

            # 8. Validate changes
            logger.info("Step 6/10: Validating changes...")
            valid, error = await self.code_analysis.validate_changes()
            if not valid:
                error_msg = f"Validation failed: {error}"
                logger.error(error_msg)
                metadata["error"] = error_msg
                # Try to cleanup: go back to main
                await self.git.pull_latest("main")
                return (False, error_msg, metadata)

            # 9. Commit changes
            logger.info("Step 7/10: Committing changes...")
            if not await self.git.commit_changes(changes_result["commit_message"]):
                error_msg = "Failed to commit changes"
                logger.error(error_msg)
                metadata["error"] = error_msg
                # Try to cleanup: go back to main
                await self.git.pull_latest("main")
                return (False, error_msg, metadata)

            # 10. Get diff for logging
            logger.info("Step 8/10: Getting diff...")
            diff = await self.git.get_diff("main")
            logger.debug("Changes diff:\n%s", diff[:1000])  # Log first 1000 chars

            # 11. Push branch
            logger.info("Step 9/10: Pushing branch to GitHub...")
            if not await self.git.push_branch(branch_name):
                error_msg = f"Failed to push branch '{branch_name}' to GitHub"
                logger.error(error_msg)
                metadata["error"] = error_msg
                return (False, error_msg, metadata)

            # 12. Create PR
            logger.info("Step 10/10: Creating pull request...")
            try:
                pr = await self.github.create_pull_request(
                    repo=self.config.github.repository,
                    title=changes_result["pr_title"],
                    body=changes_result["pr_body"],
                    head_branch=branch_name,
                    base_branch="main",
                )
                pr_url = pr["html_url"]
                pr_number = pr["number"]

                metadata["pr_url"] = pr_url
                metadata["pr_number"] = pr_number

                # Calculate execution time
                execution_time_ms = int((time.time() - start_time) * 1000)
                metadata["execution_time_ms"] = execution_time_ms

                logger.info(
                    "Self-improvement complete! PR #%d created in %dms: %s",
                    pr_number,
                    execution_time_ms,
                    pr_url,
                )

                # Return to main branch
                await self.git.pull_latest("main")

                return (True, pr_url, metadata)

            except Exception as e:
                error_msg = f"Failed to create PR: {str(e)}"
                logger.error(error_msg, exc_info=True)
                metadata["error"] = error_msg
                # Return to main branch
                await self.git.pull_latest("main")
                return (False, error_msg, metadata)

        except Exception as e:
            error_msg = f"Unexpected error during self-improvement: {str(e)}"
            logger.error(error_msg, exc_info=True)
            metadata["error"] = error_msg
            metadata["execution_time_ms"] = int((time.time() - start_time) * 1000)

            # Try to return to main branch
            try:
                await self.git.pull_latest("main")
            except Exception:
                pass  # Best effort cleanup

            return (False, error_msg, metadata)
