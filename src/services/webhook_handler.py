"""GitHub webhook event handler."""

import logging
from typing import Any

from sqlalchemy import select

from ..orm.pr_comment import PRComment
from ..orm.selfimprovement_request import SelfImprovementRequest
from .database import DatabaseService

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Routes GitHub webhook events to appropriate handlers."""

    def __init__(
        self,
        db_service: DatabaseService,
        pr_improvement_service: Any,  # Will be PRImprovementService
        owner_login: str,
    ):
        """Initialize webhook handler.

        Args:
            db_service: Database service for querying
            pr_improvement_service: Service for processing PR improvements
            owner_login: GitHub login of bot owner (e.g., "vitorpy")
        """
        self.db_service = db_service
        self.pr_improvement_service = pr_improvement_service
        self.owner_login = owner_login

    async def handle_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        delivery_id: str
    ) -> None:
        """Route webhook event to appropriate handler.

        Args:
            event_type: GitHub event type (e.g., "issue_comment")
            payload: Webhook payload
            delivery_id: GitHub delivery ID for logging
        """
        logger.info(
            f"Processing webhook event: type={event_type}, delivery_id={delivery_id}"
        )

        try:
            if event_type == "issue_comment":
                await self._handle_issue_comment(payload, delivery_id)
            elif event_type == "pull_request_review_comment":
                await self._handle_review_comment(payload, delivery_id)
            elif event_type == "ping":
                logger.info("Received ping event (webhook configured successfully)")
            else:
                logger.info(f"Ignoring unhandled event type: {event_type}")

        except Exception as e:
            logger.error(
                f"Error processing webhook event {delivery_id}: {e}",
                exc_info=True
            )

    async def _handle_issue_comment(
        self,
        payload: dict[str, Any],
        delivery_id: str
    ) -> None:
        """Handle issue comment event (general PR comments).

        Args:
            payload: Webhook payload
            delivery_id: GitHub delivery ID for logging
        """
        # Extract comment details
        action = payload.get("action")
        if action not in ["created", "edited"]:
            logger.debug(f"Ignoring issue_comment action: {action}")
            return

        comment = payload.get("comment", {})
        comment_id = comment.get("id")
        comment_body = comment.get("body", "")
        commenter_login = comment.get("user", {}).get("login", "")

        issue = payload.get("issue", {})
        pr_number = issue.get("number")

        # Only process pull requests (not regular issues)
        if "pull_request" not in issue:
            logger.debug(f"Ignoring non-PR comment: issue #{pr_number}")
            return

        logger.info(
            f"PR comment: pr_number={pr_number}, comment_id={comment_id}, "
            f"commenter={commenter_login}"
        )

        # Check if this PR was created by the bot
        if not await self._is_bot_pr(pr_number):
            logger.debug(f"Ignoring comment on non-bot PR #{pr_number}")
            return

        # Check if commenter is the owner
        if commenter_login != self.owner_login:
            logger.info(
                f"Ignoring comment from non-owner: {commenter_login} "
                f"(owner: {self.owner_login})"
            )
            return

        # Check if already processed
        if await self._is_comment_processed(comment_id):
            logger.debug(f"Comment {comment_id} already processed, skipping")
            return

        # Process the PR improvement
        await self.pr_improvement_service.process_comment(
            pr_number=pr_number,
            comment_id=comment_id,
            comment_body=comment_body,
            commenter_login=commenter_login,
            is_review_comment=False,
            file_path=None,
            diff_hunk=None,
        )

    async def _handle_review_comment(
        self,
        payload: dict[str, Any],
        delivery_id: str
    ) -> None:
        """Handle pull request review comment event (inline code comments).

        Args:
            payload: Webhook payload
            delivery_id: GitHub delivery ID for logging
        """
        # Extract comment details
        action = payload.get("action")
        if action not in ["created", "edited"]:
            logger.debug(f"Ignoring review_comment action: {action}")
            return

        comment = payload.get("comment", {})
        comment_id = comment.get("id")
        comment_body = comment.get("body", "")
        commenter_login = comment.get("user", {}).get("login", "")
        file_path = comment.get("path")
        diff_hunk = comment.get("diff_hunk")

        pull_request = payload.get("pull_request", {})
        pr_number = pull_request.get("number")

        logger.info(
            f"PR review comment: pr_number={pr_number}, comment_id={comment_id}, "
            f"commenter={commenter_login}, file={file_path}"
        )

        # Check if this PR was created by the bot
        if not await self._is_bot_pr(pr_number):
            logger.debug(f"Ignoring review comment on non-bot PR #{pr_number}")
            return

        # Check if commenter is the owner
        if commenter_login != self.owner_login:
            logger.info(
                f"Ignoring review comment from non-owner: {commenter_login} "
                f"(owner: {self.owner_login})"
            )
            return

        # Check if already processed
        if await self._is_comment_processed(comment_id):
            logger.debug(f"Review comment {comment_id} already processed, skipping")
            return

        # Process the PR improvement with file context
        await self.pr_improvement_service.process_comment(
            pr_number=pr_number,
            comment_id=comment_id,
            comment_body=comment_body,
            commenter_login=commenter_login,
            is_review_comment=True,
            file_path=file_path,
            diff_hunk=diff_hunk,
        )

    async def _is_bot_pr(self, pr_number: int) -> bool:
        """Check if PR was created by the bot via /selfimprovement.

        Args:
            pr_number: GitHub PR number

        Returns:
            True if PR was created by bot, False otherwise
        """
        async with self.db_service.session() as session:
            result = await session.execute(
                select(SelfImprovementRequest).where(
                    SelfImprovementRequest.pr_number == pr_number
                )
            )
            request = result.scalar_one_or_none()
            return request is not None

    async def _is_comment_processed(self, comment_id: int) -> bool:
        """Check if comment has already been processed.

        Args:
            comment_id: GitHub comment ID

        Returns:
            True if comment was processed, False otherwise
        """
        async with self.db_service.session() as session:
            result = await session.execute(
                select(PRComment).where(
                    PRComment.comment_id == comment_id,
                    PRComment.processed == True  # noqa: E712
                )
            )
            comment = result.scalar_one_or_none()
            return comment is not None
