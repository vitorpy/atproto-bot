"""Main bot logic with async support and database persistence."""

import asyncio
import logging

from .atproto_client import ATProtoClient, DirectMessage, Mention
from .config import Config
from .llm_handler import LLMHandler
from .services import ConversationService, DMService, MentionService, RateLimitService

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
