"""Service for iterative PR improvements via comment feedback."""

import logging
import time
from typing import Optional

from sqlalchemy import select

from ..config import Config
from ..orm.pr_comment import PRComment
from ..orm.pr_iteration import PRIteration
from ..orm.selfimprovement_request import SelfImprovementRequest
from .code_analysis_service import CodeAnalysisService
from .database import DatabaseService
from .git_service import GitService
from .github_service import GitHubService

logger = logging.getLogger(__name__)


class PRImprovementService:
    """Process PR comment feedback and apply iterative improvements."""

    def __init__(
        self,
        git_service: GitService,
        github_service: GitHubService,
        code_analysis_service: CodeAnalysisService,
        db_service: DatabaseService,
        config: Config,
    ):
        """Initialize PR improvement service.

        Args:
            git_service: Git operations service
            github_service: GitHub API service
            code_analysis_service: Code analysis service
            db_service: Database service
            config: Bot configuration
        """
        self.git = git_service
        self.github = github_service
        self.code_analysis = code_analysis_service
        self.db = db_service
        self.config = config
        logger.debug("PRImprovementService initialized")

    async def process_comment(
        self,
        pr_number: int,
        comment_id: int,
        comment_body: str,
        commenter_login: str,
        is_review_comment: bool = False,
        file_path: Optional[str] = None,
        diff_hunk: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Process PR comment and apply improvements.

        Args:
            pr_number: GitHub PR number
            comment_id: GitHub comment ID
            comment_body: Comment text
            commenter_login: GitHub login of commenter
            is_review_comment: True if inline review comment
            file_path: File path (for review comments)
            diff_hunk: Diff hunk (for review comments)

        Returns:
            Tuple of (success, message)
        """
        start_time = time.time()

        logger.info(
            f"Processing PR comment: pr={pr_number}, comment={comment_id}, "
            f"review={is_review_comment}"
        )

        try:
            # 1. Get next iteration number for this PR
            iteration_number = await self._get_next_iteration_number(pr_number)

            # 2. Mark comment as being processed
            await self._mark_comment_processing(
                pr_number, comment_id, comment_body, commenter_login
            )

            # 3. Fetch PR details
            logger.info("Step 1/10: Fetching PR details...")
            pr_data = await self.github.get_pull_request(
                repo=self.config.github.repository,
                pr_number=pr_number,
            )

            branch_name = pr_data["head"]["ref"]
            pr_title = pr_data["title"]
            pr_body = pr_data["body"] or ""

            logger.info(f"PR branch: {branch_name}")

            # 4. Checkout PR branch
            logger.info(f"Step 2/10: Checking out PR branch '{branch_name}'...")
            success = await self.git.checkout_branch(branch_name)
            if not success:
                error_msg = f"Failed to checkout branch '{branch_name}'"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 5. Pull latest changes from remote
            logger.info("Step 3/10: Pulling latest changes...")
            success = await self.git.pull_latest(branch_name)
            if not success:
                error_msg = f"Failed to pull latest changes from '{branch_name}'"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 6. Get PR diff for context
            logger.info("Step 4/10: Getting PR diff for context...")
            pr_diff = await self.git.get_diff("main")

            # 7. Build improvement prompt
            logger.info("Step 5/10: Building improvement prompt...")
            improvement_prompt = self._build_improvement_prompt(
                original_prompt=pr_title,
                pr_body=pr_body,
                pr_diff=pr_diff,
                comment_body=comment_body,
                is_review_comment=is_review_comment,
                file_path=file_path,
                diff_hunk=diff_hunk,
            )

            # 8. Analyze feedback and generate incremental changes
            logger.info("Step 6/10: Analyzing feedback and generating changes...")
            changes_result = await self.code_analysis.analyze_and_generate_changes(
                improvement_prompt, conversation_id=f"pr-{pr_number}-iteration-{iteration_number}"
            )

            if not changes_result["success"]:
                error_msg = f"Failed to generate changes: {changes_result['explanation']}"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            if not changes_result["changes"]:
                error_msg = "No changes generated from feedback"
                logger.warning(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 9. Apply changes
            logger.info(f"Step 7/10: Applying {len(changes_result['changes'])} file changes...")
            success, error = await self.code_analysis.apply_changes(changes_result["changes"])
            if not success:
                error_msg = f"Failed to apply changes: {error}"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 10. Validate changes
            logger.info("Step 8/10: Validating changes...")
            valid, error = await self.code_analysis.validate_changes()
            if not valid:
                error_msg = f"Validation failed: {error}"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 11. Commit changes
            commit_message = changes_result.get("commit_message", f"Apply feedback: {comment_body[:60]}")
            logger.info(f"Step 9/10: Committing changes: {commit_message}")
            if not await self.git.commit_changes(commit_message):
                error_msg = "Failed to commit changes"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 12. Get commit SHA
            commit_sha = await self.git.get_current_commit_sha()

            # 13. Push changes
            logger.info(f"Step 10/10: Pushing changes to branch '{branch_name}'...")
            if not await self.git.push_branch(branch_name):
                error_msg = f"Failed to push branch '{branch_name}'"
                logger.error(error_msg)
                await self._record_iteration_failure(
                    pr_number, iteration_number, comment_id, comment_body,
                    error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
                return (False, error_msg)

            # 14. Record successful iteration
            execution_time_ms = int((time.time() - start_time) * 1000)
            await self._record_iteration_success(
                pr_number, iteration_number, comment_id, comment_body,
                commit_sha, execution_time_ms
            )

            # 15. Post success comment
            success_message = self._build_success_message(
                iteration_number, commit_message, commit_sha, changes_result
            )
            await self._post_success_comment(pr_number, success_message)

            logger.info(
                f"PR improvement complete: pr={pr_number}, iteration={iteration_number}, "
                f"commit={commit_sha[:8]}, time={execution_time_ms}ms"
            )

            return (True, success_message)

        except Exception as e:
            error_msg = f"Unexpected error processing PR comment: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # Try to record failure
            try:
                execution_time_ms = int((time.time() - start_time) * 1000)
                iteration_number = await self._get_next_iteration_number(pr_number)
                await self._record_iteration_failure(
                    pr_number, iteration_number - 1 if iteration_number > 1 else 1,
                    comment_id, comment_body, error_msg, start_time
                )
                await self._post_error_comment(pr_number, error_msg)
            except Exception:
                pass  # Best effort

            return (False, error_msg)

    def _build_improvement_prompt(
        self,
        original_prompt: str,
        pr_body: str,
        pr_diff: str,
        comment_body: str,
        is_review_comment: bool,
        file_path: Optional[str],
        diff_hunk: Optional[str],
    ) -> str:
        """Build prompt for Claude to generate incremental improvements.

        Args:
            original_prompt: Original PR title/prompt
            pr_body: PR description
            pr_diff: Full PR diff
            comment_body: User's feedback comment
            is_review_comment: True if inline review comment
            file_path: File path (for review comments)
            diff_hunk: Diff hunk (for review comments)

        Returns:
            Improvement prompt for Claude
        """
        # Truncate diff if too long (keep first 5000 chars)
        max_diff_length = 5000
        truncated_diff = pr_diff[:max_diff_length]
        if len(pr_diff) > max_diff_length:
            truncated_diff += "\n... (diff truncated)"

        prompt = f"""This is an iterative improvement to an existing pull request.

**Original Request:**
{original_prompt}

**PR Description:**
{pr_body}

**Current PR Changes (diff vs main):**
```diff
{truncated_diff}
```

**User Feedback:**
{comment_body}
"""

        if is_review_comment and file_path and diff_hunk:
            prompt += f"""

**Context: Inline Review Comment**
File: {file_path}
Diff hunk:
```diff
{diff_hunk}
```
"""

        prompt += """

**Your Task:**
Generate INCREMENTAL changes that address the user's feedback while building on the existing PR changes. Do NOT rewrite the entire PR - only make targeted changes to address the specific feedback.

Focus on:
1. Understanding the feedback in context of existing changes
2. Making minimal, targeted modifications
3. Preserving existing functionality
4. Ensuring changes integrate cleanly with current PR state
"""

        return prompt

    def _build_success_message(
        self,
        iteration_number: int,
        commit_message: str,
        commit_sha: str,
        changes_result: dict,
    ) -> str:
        """Build success comment message.

        Args:
            iteration_number: Iteration number
            commit_message: Commit message
            commit_sha: Commit SHA
            changes_result: Changes result from code analysis

        Returns:
            Success message markdown
        """
        files_changed = len(changes_result.get("changes", []))

        message = f"""✅ **Changes applied** (iteration {iteration_number})

**Summary:** {changes_result.get('explanation', 'Applied requested changes')}

**Commit:** `{commit_sha[:8]}` - {commit_message}

**Files modified:** {files_changed}
"""
        return message

    async def _get_next_iteration_number(self, pr_number: int) -> int:
        """Get next iteration number for PR.

        Args:
            pr_number: GitHub PR number

        Returns:
            Next iteration number (1, 2, 3, ...)
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(PRIteration.iteration_number)
                .where(PRIteration.pr_number == pr_number)
                .order_by(PRIteration.iteration_number.desc())
                .limit(1)
            )
            last_iteration = result.scalar_one_or_none()
            return (last_iteration or 0) + 1

    async def _mark_comment_processing(
        self,
        pr_number: int,
        comment_id: int,
        comment_body: str,
        commenter_login: str,
    ) -> None:
        """Mark comment as being processed.

        Args:
            pr_number: GitHub PR number
            comment_id: GitHub comment ID
            comment_body: Comment text
            commenter_login: GitHub login
        """
        async with self.db.session() as session:
            # Check if already exists
            result = await session.execute(
                select(PRComment).where(PRComment.comment_id == comment_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.processed = True
            else:
                # Get selfimprovement_request_id if exists
                si_result = await session.execute(
                    select(SelfImprovementRequest.id).where(
                        SelfImprovementRequest.pr_number == pr_number
                    )
                )
                si_request_id = si_result.scalar_one_or_none()

                comment = PRComment(
                    pr_number=pr_number,
                    comment_id=comment_id,
                    comment_body=comment_body,
                    commenter_login=commenter_login,
                    processed=True,
                    selfimprovement_request_id=si_request_id,
                )
                session.add(comment)

    async def _record_iteration_success(
        self,
        pr_number: int,
        iteration_number: int,
        comment_id: int,
        comment_body: str,
        commit_sha: str,
        execution_time_ms: int,
    ) -> None:
        """Record successful PR iteration.

        Args:
            pr_number: GitHub PR number
            iteration_number: Iteration number
            comment_id: GitHub comment ID
            comment_body: Comment text
            commit_sha: Commit SHA
            execution_time_ms: Execution time in milliseconds
        """
        async with self.db.session() as session:
            iteration = PRIteration(
                pr_number=pr_number,
                iteration_number=iteration_number,
                comment_id=comment_id,
                comment_body=comment_body,
                commit_sha=commit_sha,
                success=True,
                error_message=None,
                execution_time_ms=execution_time_ms,
            )
            session.add(iteration)

    async def _record_iteration_failure(
        self,
        pr_number: int,
        iteration_number: int,
        comment_id: int,
        comment_body: str,
        error_message: str,
        start_time: float,
    ) -> None:
        """Record failed PR iteration.

        Args:
            pr_number: GitHub PR number
            iteration_number: Iteration number
            comment_id: GitHub comment ID
            comment_body: Comment text
            error_message: Error message
            start_time: Start time (for calculating execution time)
        """
        execution_time_ms = int((time.time() - start_time) * 1000)

        async with self.db.session() as session:
            iteration = PRIteration(
                pr_number=pr_number,
                iteration_number=iteration_number,
                comment_id=comment_id,
                comment_body=comment_body,
                commit_sha=None,
                success=False,
                error_message=error_message,
                execution_time_ms=execution_time_ms,
            )
            session.add(iteration)

    async def _post_success_comment(self, pr_number: int, message: str) -> None:
        """Post success comment on PR.

        Args:
            pr_number: GitHub PR number
            message: Success message
        """
        try:
            await self.github.post_pr_comment(
                repo=self.config.github.repository,
                pr_number=pr_number,
                body=message,
            )
        except Exception as e:
            logger.error(f"Failed to post success comment: {e}", exc_info=True)

    async def _post_error_comment(self, pr_number: int, error_msg: str) -> None:
        """Post error comment on PR.

        Args:
            pr_number: GitHub PR number
            error_msg: Error message
        """
        message = f"""❌ **Failed to apply changes**

**Error:** {error_msg}

Please check the error and try again with clarified feedback.
"""
        try:
            await self.github.post_pr_comment(
                repo=self.config.github.repository,
                pr_number=pr_number,
                body=message,
            )
        except Exception as e:
            logger.error(f"Failed to post error comment: {e}", exc_info=True)
