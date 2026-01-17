"""FastAPI webhook server for GitHub webhooks."""

import hmac
import hashlib
import logging
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import Config

logger = logging.getLogger(__name__)


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature using HMAC SHA-256.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value (format: "sha256=...")
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature.startswith("sha256="):
        logger.warning("Invalid signature format (missing sha256= prefix)")
        return False

    # Extract the signature hash
    received_signature = signature[7:]  # Remove "sha256=" prefix

    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, received_signature)

    if not is_valid:
        logger.warning(
            "Signature verification failed. "
            f"Expected: {expected_signature[:16]}..., "
            f"Received: {received_signature[:16]}..."
        )

    return is_valid


def create_webhook_app(config: Config, webhook_handler: Any) -> FastAPI:
    """Create and configure the FastAPI webhook application.

    Args:
        config: Application configuration
        webhook_handler: WebhookHandler instance

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="ATProto Bot Webhooks",
        description="GitHub webhook receiver for PR comment automation",
        version="1.0.0"
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "atproto-bot-webhooks"
        }

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks
    ) -> JSONResponse:
        """Handle incoming GitHub webhooks.

        Security:
        - Verifies HMAC signature before processing
        - Returns 401 for invalid signatures
        - Processes events in background to return quickly

        Returns:
            200 response immediately, processes event in background
        """
        # Get request data
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        event_type = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")

        # Log webhook receipt
        logger.info(
            f"Received GitHub webhook: event={event_type}, "
            f"delivery_id={delivery_id}"
        )

        # Verify signature BEFORE any processing
        if not config.github or not config.github.webhook_secret:
            logger.error("GitHub webhook secret not configured")
            raise HTTPException(
                status_code=500,
                detail="Webhook secret not configured"
            )

        webhook_secret = config.github.webhook_secret.get_secret_value()
        if not verify_github_signature(body, signature, webhook_secret):
            logger.warning(
                f"Invalid webhook signature for event={event_type}, "
                f"delivery_id={delivery_id}"
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid signature"
            )

        # Parse payload (signature verified, safe to parse)
        try:
            import json
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON payload"
            )

        # Process webhook in background (return 200 quickly to GitHub)
        background_tasks.add_task(
            webhook_handler.handle_event,
            event_type,
            payload,
            delivery_id
        )

        logger.info(f"Accepted webhook event={event_type}, delivery_id={delivery_id}")

        return JSONResponse(
            {"status": "accepted", "delivery_id": delivery_id},
            status_code=200
        )

    return app
