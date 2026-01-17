"""ATproto client wrapper for Bluesky interactions."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from atproto import Client, models

from .config import BlueskyConfig

logger = logging.getLogger(__name__)


@dataclass
class ThreadPost:
    """Represents a single post in a thread."""

    uri: str
    cid: str
    author_handle: str
    author_did: str
    text: str
    created_at: datetime
    reply_parent: str | None = None
    reply_root: str | None = None

    def __str__(self) -> str:
        return f"@{self.author_handle}: {self.text}"


@dataclass
class Mention:
    """Represents a mention notification."""

    uri: str
    cid: str
    author_did: str
    author_handle: str
    text: str
    indexed_at: datetime
    root_uri: str | None = None


@dataclass
class DirectMessage:
    """Represents a direct message."""

    convo_id: str
    message_id: str
    rev: str
    sender_did: str
    sender_handle: str
    text: str
    sent_at: datetime


class ATProtoClient:
    """Wrapper around the ATproto client for bot operations."""

    def __init__(self, config: BlueskyConfig) -> None:
        self.config = config
        self.client = Client()
        self._logged_in = False

    def login(self) -> None:
        """Authenticate with Bluesky."""
        if self._logged_in:
            return

        logger.info("Logging in as %s", self.config.handle)
        self.client.login(
            self.config.handle,
            self.config.app_password.get_secret_value(),
        )
        self._logged_in = True
        logger.info("Successfully logged in")

    def get_unread_mentions(self, owner_did: str) -> list[Mention]:
        """Fetch unread mention notifications from the owner.

        Args:
            owner_did: Only return mentions from this DID.

        Returns:
            List of Mention objects from the owner.
        """
        self.login()

        mentions: list[Mention] = []
        cursor = None

        while True:
            response = self.client.app.bsky.notification.list_notifications(
                params={"limit": 50, "cursor": cursor}
            )

            for notif in response.notifications:
                # Only process mentions
                if notif.reason != "mention":
                    continue

                # Only process from owner
                if notif.author.did != owner_did:
                    logger.debug("Ignoring mention from non-owner: %s", notif.author.handle)
                    continue

                # Skip if already read
                if notif.is_read:
                    continue

                # Extract root URI for thread context
                root_uri = None
                if hasattr(notif.record, "reply") and notif.record.reply:
                    root_uri = notif.record.reply.root.uri

                mentions.append(
                    Mention(
                        uri=notif.uri,
                        cid=notif.cid,
                        author_did=notif.author.did,
                        author_handle=notif.author.handle,
                        text=notif.record.text,
                        indexed_at=datetime.fromisoformat(notif.indexed_at.replace("Z", "+00:00")),
                        root_uri=root_uri,
                    )
                )

            cursor = response.cursor
            if not cursor:
                break

        return mentions

    def mark_notifications_read(self) -> None:
        """Mark all notifications as read."""
        self.login()
        self.client.app.bsky.notification.update_seen(
            data={"seen_at": datetime.now(timezone.utc).isoformat()}
        )

    def get_thread(self, uri: str, max_depth: int = 50) -> list[ThreadPost]:
        """Fetch a thread starting from a post URI.

        Args:
            uri: The AT URI of any post in the thread.
            max_depth: Maximum depth to traverse.

        Returns:
            List of ThreadPost objects in chronological order.
        """
        self.login()

        response = self.client.app.bsky.feed.get_post_thread(
            params={"uri": uri, "depth": max_depth, "parentHeight": max_depth}
        )

        posts: list[ThreadPost] = []
        self._collect_thread_posts(response.thread, posts)

        # Sort by creation time
        posts.sort(key=lambda p: p.created_at)
        return posts

    def _collect_thread_posts(
        self,
        thread: models.AppBskyFeedDefs.ThreadViewPost
        | models.AppBskyFeedDefs.NotFoundPost
        | models.AppBskyFeedDefs.BlockedPost,
        posts: list[ThreadPost],
    ) -> None:
        """Recursively collect posts from thread structure."""
        # Skip blocked or not found posts
        if isinstance(
            thread,
            (models.AppBskyFeedDefs.NotFoundPost, models.AppBskyFeedDefs.BlockedPost),
        ):
            return

        post = thread.post

        # Extract reply info
        reply_parent = None
        reply_root = None
        if hasattr(post.record, "reply") and post.record.reply:
            reply_parent = post.record.reply.parent.uri
            reply_root = post.record.reply.root.uri

        thread_post = ThreadPost(
            uri=post.uri,
            cid=post.cid,
            author_handle=post.author.handle,
            author_did=post.author.did,
            text=post.record.text,
            created_at=datetime.fromisoformat(post.record.created_at.replace("Z", "+00:00")),
            reply_parent=reply_parent,
            reply_root=reply_root,
        )

        # Avoid duplicates
        if not any(p.uri == thread_post.uri for p in posts):
            posts.append(thread_post)

        # Traverse parent
        if hasattr(thread, "parent") and thread.parent:
            self._collect_thread_posts(thread.parent, posts)

        # Traverse replies
        if hasattr(thread, "replies") and thread.replies:
            for reply in thread.replies:
                self._collect_thread_posts(reply, posts)

    def reply_to_post(
        self,
        text: str,
        reply_to_uri: str,
        reply_to_cid: str,
        root_uri: str | None = None,
        root_cid: str | None = None,
    ) -> str:
        """Post a reply.

        Args:
            text: The reply text.
            reply_to_uri: URI of the post being replied to.
            reply_to_cid: CID of the post being replied to.
            root_uri: URI of the thread root (defaults to reply_to_uri).
            root_cid: CID of the thread root (defaults to reply_to_cid).

        Returns:
            URI of the created post.
        """
        self.login()

        # If no root specified, the reply target is the root
        if root_uri is None:
            root_uri = reply_to_uri
        if root_cid is None:
            root_cid = reply_to_cid

        reply_ref = models.AppBskyFeedPost.ReplyRef(
            root=models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid),
            parent=models.ComAtprotoRepoStrongRef.Main(uri=reply_to_uri, cid=reply_to_cid),
        )

        response = self.client.send_post(text=text, reply_to=reply_ref)
        logger.info("Posted reply: %s", response.uri)
        return response.uri

    def get_post(self, uri: str) -> ThreadPost:
        """Fetch a single post by URI.

        Args:
            uri: The AT URI of the post.

        Returns:
            ThreadPost object.
        """
        self.login()

        # Parse the URI to get repo and rkey
        # Format: at://did:plc:xxx/app.bsky.feed.post/rkey
        response = self.client.app.bsky.feed.get_posts(params={"uris": [uri]})

        if not response.posts:
            raise ValueError(f"Post not found: {uri}")

        post = response.posts[0]

        reply_parent = None
        reply_root = None
        if hasattr(post.record, "reply") and post.record.reply:
            reply_parent = post.record.reply.parent.uri
            reply_root = post.record.reply.root.uri

        return ThreadPost(
            uri=post.uri,
            cid=post.cid,
            author_handle=post.author.handle,
            author_did=post.author.did,
            text=post.record.text,
            created_at=datetime.fromisoformat(post.record.created_at.replace("Z", "+00:00")),
            reply_parent=reply_parent,
            reply_root=reply_root,
        )

    def get_unread_dms(self, owner_did: str) -> list[DirectMessage]:
        """Fetch unread DMs from owner.

        Args:
            owner_did: DID of the bot owner (only process DMs from them).

        Returns:
            List of unread DirectMessage objects from owner.
        """
        try:
            self.login()

            # Create chat-proxied client
            dm_client = self.client.with_bsky_chat_proxy()

            # List conversations
            convos_response = dm_client.chat.bsky.convo.list_convos(params={"limit": 50})

            dms = []

            for convo in convos_response.convos:
                # Skip if no unread messages
                if convo.unread_count == 0:
                    continue

                # Check if conversation is with owner (2 members: bot + owner)
                member_dids = [m.did for m in convo.members]
                if owner_did not in member_dids:
                    continue

                # Create DID to handle mapping from conversation members
                # MessageViewSender only has 'did', but ProfileViewBasic has both 'did' and 'handle'
                did_to_handle = {m.did: m.handle for m in convo.members}

                # Fetch messages in this conversation
                messages_response = dm_client.chat.bsky.convo.get_messages(
                    params={"convo_id": convo.id, "limit": 100}
                )

                # Find unread messages from owner
                for msg in messages_response.messages:
                    # Skip messages from bot itself
                    if msg.sender.did == self.client.me.did:
                        continue

                    # Only process messages from owner
                    if msg.sender.did != owner_did:
                        continue

                    # Create DirectMessage object
                    dm = DirectMessage(
                        convo_id=convo.id,
                        message_id=msg.id,
                        rev=msg.rev,
                        sender_did=msg.sender.did,
                        sender_handle=did_to_handle.get(msg.sender.did, msg.sender.did),
                        text=msg.text,
                        sent_at=msg.sent_at,
                    )
                    dms.append(dm)

            return dms

        except Exception as e:
            logger.error("Error fetching DMs: %s", e, exc_info=True)
            return []

    def send_dm(self, convo_id: str, text: str) -> str:
        """Send a DM reply.

        Args:
            convo_id: Conversation ID to reply to.
            text: Message text to send.

        Returns:
            Message ID of sent message.
        """
        self.login()

        # Create chat-proxied client
        dm_client = self.client.with_bsky_chat_proxy()

        # Send message
        response = dm_client.chat.bsky.convo.send_message(
            data={
                "convo_id": convo_id,
                "message": models.ChatBskyConvoDefs.MessageInput(text=text),
            }
        )

        logger.debug("Sent DM to conversation %s", convo_id)
        return response.id

    def mark_dm_read(self, convo_id: str, message_id: str) -> None:
        """Mark a DM as read.

        Args:
            convo_id: Conversation ID.
            message_id: Message ID to mark as read.
        """
        self.login()

        dm_client = self.client.with_bsky_chat_proxy()
        dm_client.chat.bsky.convo.update_read(data={"convo_id": convo_id, "message_id": message_id})
