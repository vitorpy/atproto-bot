"""Main bot logic with async support and database persistence."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from .atproto_client import ATProtoClient, DirectMessage, Mention
from .command_router import CommandRouter, CommandType
from .config import Config
from .llm_handler import LLMHandler
from .orm import SelfImprovementRequest
from .services import ConversationService, DMService, MentionService, RateLimitService
from .services.code_analysis_service import CodeAnalysisService
from .services.git_service import GitService
from .services.github_service import GitHubService
from .services.selfimprovement_service import SelfImprovementService

logger = logging.getLogger(__name__)


class Bot:
    """Main bot orchestrator with async support and database persistence."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.atproto = ATProtoClient(config.bluesky)
        self.llm = LLMHandler(config.llm)

        # Use database-backed services
        self.mention_service = MentionService()
        self.dm_service = DMService()
        self.rate_limit_service = RateLimitService(config.bot.rate_limit_per_hour)
        self.conversation_service = ConversationService()

        # Command router for slash commands
        self.command_router = CommandRouter()

        # Self-improvement service (lazy init - only if GitHub configured)
        self.selfimprovement_service: Optional[SelfImprovementService] = None

    def _init_selfimprovement_service(self, repo_path: str = "/var/www/atproto-bot") -> None:
        """
        Lazy initialization of self-improvement service.

        Only initializes if GitHub is configured in config.

        Args:
            repo_path: Path to the repository (default: deployment path).
        """
        if not self.config.github:
            logger.warning("GitHub not configured, self-improvement service unavailable")
            return

        try:
            logger.info("Initializing self-improvement service...")

            # Initialize Git service
            git_service = GitService(repo_path=repo_path)

            # Initialize GitHub service
            github_service = GitHubService(
                app_id=self.config.github.app_id,
                private_key=self.config.github.private_key.get_secret_value(),
                installation_id=self.config.github.installation_id,
            )

            # Initialize Code Analysis service
            code_analysis_service = CodeAnalysisService(
                llm=self.llm.llm,  # Access underlying LLM
                repo_path=repo_path,
            )

            # Initialize orchestrator
            self.selfimprovement_service = SelfImprovementService(
                git_service=git_service,
                github_service=github_service,
                code_analysis_service=code_analysis_service,
                config=self.config,
            )

            logger.info("Self-improvement service initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize self-improvement service: %s", e, exc_info=True)
            self.selfimprovement_service = None

    async def _handle_command(self, command, mention: Mention) -> bool:
        """
        Handle parsed slash command.

        Args:
            command: ParsedCommand object.
            mention: The mention that triggered the command.

        Returns:
            True if command was handled successfully.
        """
        # Mark as processed IMMEDIATELY to prevent duplicate processing
        # Extract thread URI (needed for normal mentions, not DMs)
        thread_uri = mention.root_uri or mention.uri if not mention.uri.startswith("dm://") else mention.uri

        await self.mention_service.mark_processed(
            mention_uri=mention.uri,
            author_did=mention.author_did,
            author_handle=mention.author_handle,
            mention_text=getattr(mention, 'text', ''),
            reply_uri="",  # Will be updated after replies are sent
            thread_uri=thread_uri,
        )

        if command.command_type == CommandType.SELFIMPROVEMENT:
            # Initialize service if not already done
            if self.selfimprovement_service is None:
                self._init_selfimprovement_service()

            # Check if service is available
            if self.selfimprovement_service is None:
                await self._reply_to_mention(
                    mention,
                    "Self-improvement not configured. Please configure GitHub App credentials.",
                )
                return True

            # Send initial reply
            await self._reply_to_mention(
                mention,
                "Starting self-improvement process... This may take a few minutes. I'll reply when done.",
            )

            # Execute self-improvement
            logger.info("Executing self-improvement for prompt: %s", command.arguments)
            success, result_message, metadata = await self.selfimprovement_service.execute_selfimprovement(
                prompt=command.arguments,
                requester_did=mention.author_did,
                conversation_id=mention.uri,
            )

            # Store request in database
            await self._store_selfimprovement_request(
                conversation_id=mention.uri,
                requester_did=mention.author_did,
                prompt=command.arguments,
                success=success,
                metadata=metadata,
            )

            # Send result reply
            if success:
                message = (
                    f"✅ Self-improvement complete!\n\n"
                    f"Pull request created: {result_message}\n\n"
                    f"Review and merge when ready."
                )
            else:
                message = f"❌ Self-improvement failed:\n\n{result_message}"

            await self._reply_to_mention(mention, message)

            # Record rate limit event
            await self.rate_limit_service.record_request(
                user_did=mention.author_did, mention_uri=mention.uri
            )

            return True

        # Unknown command (shouldn't happen due to enum, but be safe)
        logger.warning("Unknown command type: %s", command.command_type)
        return False

    async def _reply_to_mention(self, mention, text: str) -> None:
        """
        Helper method to reply to a mention or DM.

        Args:
            mention: The mention or DM wrapper to reply to.
            text: Reply text.
        """
        # Check if this is a DM (URI starts with "dm://")
        if hasattr(mention, 'uri') and mention.uri.startswith("dm://"):
            # Extract convo_id from URI (format: dm://convo_id/message_id)
            parts = mention.uri.replace("dm://", "").split("/")
            if len(parts) >= 1:
                convo_id = parts[0]
                self.atproto.send_dm(convo_id=convo_id, text=text)
                logger.debug("Sent DM reply to @%s: %s", mention.author_handle, text[:50])
        else:
            # Regular mention - post public reply
            # Find root post info for proper threading
            root_uri = mention.root_uri or mention.uri
            root_cid = None

            if mention.root_uri:
                # Fetch root post to get its CID
                root_post = self.atproto.get_post(mention.root_uri)
                root_cid = root_post.cid

            # Post reply
            self.atproto.reply_to_post(
                text=text,
                reply_to_uri=mention.uri,
                reply_to_cid=mention.cid,
                root_uri=root_uri,
                root_cid=root_cid,
            )
            logger.debug("Sent reply to @%s: %s", mention.author_handle, text[:50])

    async def _store_selfimprovement_request(
        self,
        conversation_id: str,
        requester_did: str,
        prompt: str,
        success: bool,
        metadata: dict,
    ) -> None:
        """
        Store self-improvement request in database.

        Args:
            conversation_id: Thread/DM URI.
            requester_did: DID of requester.
            prompt: Improvement request text.
            success: Whether the request succeeded.
            metadata: Metadata dict with branch_name, pr_number, pr_url, error, execution_time_ms.
        """
        from .services.database import get_db

        try:
            db = get_db()
            async with db.session() as session:
                request = SelfImprovementRequest(
                    conversation_id=conversation_id,
                    requester_did=requester_did,
                    prompt=prompt,
                    branch_name=metadata.get("branch_name"),
                    pr_number=metadata.get("pr_number"),
                    pr_url=metadata.get("pr_url"),
                    success=success,
                    error_message=metadata.get("error"),
                    execution_time_ms=metadata.get("execution_time_ms"),
                )
                session.add(request)
                await session.commit()
                logger.debug("Stored self-improvement request in database: %s", request.id)

        except Exception as e:
            logger.error("Failed to store self-improvement request: %s", e, exc_info=True)

    async def process_mention(self, mention: Mention) -> bool:
        """Process a single mention with database persistence.

        Args:
            mention: The mention to process.

        Returns:
            True if successfully processed.
        """
        # Check if already processed (database check)
        if await self.mention_service.is_processed(mention.uri):
            logger.debug("Skipping already processed mention: %s", mention.uri)
            return False

        # Rate limiting (database check)
        if not await self.rate_limit_service.is_allowed(mention.author_did):
            remaining = await self.rate_limit_service.get_remaining(mention.author_did)
            logger.warning(
                "Rate limit exceeded for user %s (%s remaining)",
                mention.author_handle,
                remaining,
            )
            return False

        logger.info(
            "Processing mention from @%s: %s",
            mention.author_handle,
            mention.text[:50] + "..." if len(mention.text) > 50 else mention.text,
        )

        # Check for slash command BEFORE LLM processing
        parsed_command = self.command_router.parse_command(mention.text, self.config.bluesky.handle)
        if parsed_command:
            logger.info("Detected slash command: /%s", parsed_command.command_type.value)
            return await self._handle_command(parsed_command, mention)

        try:
            # Fetch thread context
            thread_uri = mention.root_uri or mention.uri
            thread = self.atproto.get_thread(thread_uri, max_depth=self.config.bot.max_thread_depth)

            logger.debug("Fetched thread with %d posts", len(thread))

            # Get conversation history for this thread
            conversation_history = await self.conversation_service.get_thread_history(
                thread_uri=thread_uri, limit=10
            )

            if conversation_history:
                logger.debug("Found %d previous conversation entries", len(conversation_history))

            # Generate response with tool calling
            response_text = await self.llm.generate_response_with_tools(
                thread=thread,
                mention_text=mention.text,
                bot_handle=self.config.bluesky.handle,
                max_length=self.config.bot.max_post_length,
                conversation_history=conversation_history,
                conversation_id=thread_uri,
            )

            logger.debug("Generated response: %s", response_text)

            # Find root post info for proper threading
            root_uri = mention.root_uri or mention.uri
            root_cid = None

            if mention.root_uri:
                # Fetch root post to get its CID
                root_post = self.atproto.get_post(mention.root_uri)
                root_cid = root_post.cid

            # Post reply
            self.atproto.reply_to_post(
                text=response_text,
                reply_to_uri=mention.uri,
                reply_to_cid=mention.cid,
                root_uri=root_uri,
                root_cid=root_cid,
            )

            # Build reply URI (approximate - exact format depends on API response)
            reply_uri = (
                f"at://{self.config.bluesky.handle}/app.bsky.feed.post/{mention.uri.split('/')[-1]}"
            )

            # Mark as processed in database
            processed = await self.mention_service.mark_processed(
                mention_uri=mention.uri,
                author_did=mention.author_did,
                author_handle=mention.author_handle,
                mention_text=mention.text,
                reply_uri=reply_uri,
                thread_uri=thread_uri,
            )

            # Store conversation turn
            await self.conversation_service.store_conversation_turn(
                thread_uri=thread_uri,
                mention_id=processed.id,
                user_message=mention.text,
                assistant_message=response_text,
                author_did=mention.author_did,
                user_post_uri=mention.uri,
                assistant_post_uri=reply_uri,
            )

            # Record rate limit event
            await self.rate_limit_service.record_request(
                user_did=mention.author_did, mention_uri=mention.uri
            )

            logger.info("Successfully replied to @%s", mention.author_handle)
            return True

        except Exception as e:
            logger.error("Error processing mention %s: %s", mention.uri, e, exc_info=True)
            # Don't mark as processed if we failed - allow retry
            return False

    async def process_dm(self, dm: DirectMessage) -> bool:
        """Process a single DM with database persistence.

        Args:
            dm: The DirectMessage to process.

        Returns:
            True if successfully processed.
        """
        # Check if already processed (database check)
        if await self.dm_service.is_processed(dm.message_id):
            return False

        # Rate limiting (shared with mentions - database check)
        if not await self.rate_limit_service.is_allowed(dm.sender_did):
            remaining = await self.rate_limit_service.get_remaining(dm.sender_did)
            logger.warning(
                "Rate limit exceeded for user %s (%s remaining)",
                dm.sender_handle,
                remaining,
            )
            return False

        logger.info(
            "Processing DM from @%s: %s",
            dm.sender_handle,
            dm.text[:50] + "..." if len(dm.text) > 50 else dm.text,
        )

        # Check for slash command BEFORE LLM processing
        # For DMs, bot handle might not be mentioned, so pass empty handle for DM-only commands
        parsed_command = self.command_router.parse_command(dm.text, self.config.bluesky.handle)
        if parsed_command:
            logger.info("Detected slash command in DM: /%s", parsed_command.command_type.value)
            # Convert DM to mention-like object for command handling
            # (We need to adapt _handle_command to work with DMs too)
            # For now, create a simple wrapper
            class DMWrapper:
                def __init__(self, dm):
                    self.uri = f"dm://{dm.convo_id}/{dm.message_id}"
                    self.author_did = dm.sender_did
                    self.author_handle = dm.sender_handle
                    self.text = dm.text
                    self.cid = dm.message_id  # Use message_id as cid
                    self.root_uri = None

            mention_like = DMWrapper(dm)
            return await self._handle_command(parsed_command, mention_like)

        try:
            # Get conversation history for this DM thread (using convo_id as thread_uri)
            conversation_history = await self.conversation_service.get_thread_history(
                thread_uri=dm.convo_id, limit=10
            )

            if conversation_history:
                logger.debug("Found %d previous conversation entries", len(conversation_history))

            # Generate response with tool calling
            # Note: For DMs, thread context is empty (no public posts)
            response_text = await self.llm.generate_response_with_tools(
                thread=[],  # No public thread for DMs
                mention_text=dm.text,
                bot_handle=self.config.bluesky.handle,
                max_length=10000,  # DMs support up to 10k characters
                conversation_history=conversation_history,
                channel="dm",  # Tell LLM this is a private DM
                conversation_id=dm.convo_id,
            )

            logger.debug("Generated DM response: %s", response_text)

            # Send DM reply
            reply_message_id = self.atproto.send_dm(convo_id=dm.convo_id, text=response_text)

            # Mark DM as read
            self.atproto.mark_dm_read(convo_id=dm.convo_id, message_id=dm.message_id)

            # Mark as processed in database
            processed = await self.dm_service.mark_processed(
                convo_id=dm.convo_id,
                message_id=dm.message_id,
                sender_did=dm.sender_did,
                sender_handle=dm.sender_handle,
                message_text=dm.text,
                reply_message_id=reply_message_id,
            )

            # Store conversation turn (using convo_id as thread_uri)
            await self.conversation_service.store_conversation_turn(
                thread_uri=dm.convo_id,
                mention_id=processed.id,
                user_message=dm.text,
                assistant_message=response_text,
                author_did=dm.sender_did,
                user_post_uri=f"dm://{dm.convo_id}/{dm.message_id}",
                assistant_post_uri=f"dm://{dm.convo_id}/{reply_message_id}",
            )

            # Record rate limit event (shared with mentions)
            await self.rate_limit_service.record_request(
                user_did=dm.sender_did, mention_uri=f"dm://{dm.convo_id}/{dm.message_id}"
            )

            logger.info("Successfully replied to DM from @%s", dm.sender_handle)
            return True

        except Exception as e:
            logger.error("Error processing DM %s: %s", dm.message_id, e, exc_info=True)
            # Don't mark as processed if we failed - allow retry
            return False

    async def run_once(self) -> int:
        """Run a single polling cycle for both mentions and DMs.

        Returns:
            Number of items processed (mentions + DMs).
        """
        logger.debug("Checking for new mentions and DMs...")

        try:
            # Fetch both mentions and DMs
            mentions = self.atproto.get_unread_mentions(self.config.bluesky.owner_did)
            dms = self.atproto.get_unread_dms(self.config.bluesky.owner_did)

            if mentions:
                logger.info("Found %d new mention(s) from owner", len(mentions))
            if dms:
                logger.info("Found %d new DM(s) from owner", len(dms))

            processed = 0

            # Process mentions
            for mention in mentions:
                if await self.process_mention(mention):
                    processed += 1

            # Process DMs
            for dm in dms:
                if await self.process_dm(dm):
                    processed += 1

            # Mark notifications as read after processing mentions
            if mentions:
                self.atproto.mark_notifications_read()

            # Note: DMs are marked read individually in process_dm()

            return processed

        except Exception as e:
            logger.error("Error in polling cycle: %s", e, exc_info=True)
            return 0

    async def run(self) -> None:
        """Run the bot in a continuous polling loop."""
        logger.info("Starting bot for @%s", self.config.bluesky.handle)
        logger.info("Listening for mentions from owner: %s", self.config.bluesky.owner_did)
        logger.info("Poll interval: %d seconds", self.config.bot.poll_interval)

        # Initial login
        self.atproto.login()

        try:
            while True:
                await self.run_once()
                await asyncio.sleep(self.config.bot.poll_interval)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, exiting...")
        except Exception as e:
            logger.error("Unexpected error in main loop: %s", e, exc_info=True)
            raise
