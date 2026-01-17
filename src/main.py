"""Main entry point for the ATproto bot."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .bot import Bot
from .config import load_config
from .services import get_db_service, init_db_service
from .services.code_analysis_service import CodeAnalysisService
from .services.git_service import GitService
from .services.github_service import GitHubService
from .services.pr_improvement_service import PRImprovementService
from .services.webhook_handler import WebhookHandler
from .webhook_server import create_webhook_app


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


async def run_webhook_server(args, logger, config) -> None:
    """Run webhook server."""
    try:
        import uvicorn

        logger.info("Starting webhook server on port %d...", args.webhook_port)

        # Initialize services for webhook handling
        db_service = get_db_service()

        if not config.github:
            logger.error("GitHub configuration required for webhook server")
            return

        # Get repo path from environment or use current directory
        repo_path = Path.cwd()

        # Initialize services
        git_service = GitService(repo_path)
        github_service = GitHubService(
            app_id=config.github.app_id,
            private_key=config.github.private_key.get_secret_value(),
            installation_id=config.github.installation_id,
        )
        code_analysis_service = CodeAnalysisService(
            llm_config=config.llm,
            repo_path=repo_path,
        )
        pr_improvement_service = PRImprovementService(
            git_service=git_service,
            github_service=github_service,
            code_analysis_service=code_analysis_service,
            db_service=db_service,
            config=config,
        )

        # Get owner GitHub login from environment or config
        # For now, hardcode to "vitorpy" (can be made configurable later)
        owner_login = "vitorpy"

        webhook_handler = WebhookHandler(
            db_service=db_service,
            pr_improvement_service=pr_improvement_service,
            owner_login=owner_login,
        )

        # Create FastAPI app
        app = create_webhook_app(config, webhook_handler)

        # Run uvicorn server
        uvicorn_config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=args.webhook_port,
            log_level="info" if args.verbose else "warning",
        )
        server = uvicorn.Server(uvicorn_config)
        await server.serve()

    except ImportError:
        logger.error("uvicorn not installed. Install with: pip install uvicorn[standard]")
    except Exception as e:
        logger.exception("Webhook server error: %s", e)


async def run_combined(args, logger, config) -> None:
    """Run both polling bot and webhook server concurrently."""
    logger.info("Starting combined mode (polling + webhook)")

    # Create tasks for both modes
    polling_task = asyncio.create_task(async_main(args, logger))
    webhook_task = asyncio.create_task(run_webhook_server(args, logger, config))

    # Wait for either task to complete (or fail)
    done, pending = await asyncio.wait(
        [polling_task, webhook_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # Cancel pending tasks
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Get result from completed task
    for task in done:
        try:
            return task.result()
        except Exception as e:
            logger.exception("Task failed: %s", e)


async def async_main(args, logger) -> int:
    """Async main function (polling mode)."""
    try:
        logger.info("Loading configuration from %s", args.config)
        config = load_config(args.config)

        # Initialize database
        logger.info("Initializing database at %s", config.bot.database_path)
        await init_db_service(config.bot.database_path)
        logger.info("Database initialized successfully")

        bot = Bot(config)

        if args.once:
            logger.info("Running single poll cycle...")
            processed = await bot.run_once()
            logger.info("Processed %d mention(s)", processed)
        else:
            await bot.run()

        return 0

    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1
    finally:
        # Clean up database connection
        try:
            db = get_db_service()
            await db.close()
            logger.info("Database connection closed")
        except RuntimeError:
            # Database wasn't initialized (error during startup)
            pass


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ATproto/Bluesky bot with LLM integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Run with default config.yaml (polling mode)
  %(prog)s -c myconfig.yaml             # Run with custom config
  %(prog)s -v                           # Run with verbose logging
  %(prog)s --once                       # Process once and exit (useful for testing)
  %(prog)s --mode webhook               # Run webhook server only
  %(prog)s --mode combined              # Run both polling + webhook
  %(prog)s --mode combined --webhook-port 8080  # Combined mode with custom port
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't poll continuously)",
    )
    parser.add_argument(
        "--mode",
        choices=["polling", "webhook", "combined"],
        default="polling",
        help="Run mode: polling (default), webhook only, or combined",
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=8080,
        help="Port for webhook server (default: 8080)",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Route to appropriate mode
    if args.mode == "webhook":
        # Webhook mode: Load config first, then run webhook server
        try:
            logger.info("Loading configuration from %s", args.config)
            config = load_config(args.config)

            # Initialize database
            logger.info("Initializing database at %s", config.bot.database_path)
            asyncio.run(init_db_service(config.bot.database_path))
            logger.info("Database initialized successfully")

            return asyncio.run(run_webhook_server(args, logger, config))
        except Exception as e:
            logger.exception("Fatal error: %s", e)
            return 1

    elif args.mode == "combined":
        # Combined mode: Load config first, then run both
        try:
            logger.info("Loading configuration from %s", args.config)
            config = load_config(args.config)

            # Initialize database
            logger.info("Initializing database at %s", config.bot.database_path)
            asyncio.run(init_db_service(config.bot.database_path))
            logger.info("Database initialized successfully")

            return asyncio.run(run_combined(args, logger, config))
        except Exception as e:
            logger.exception("Fatal error: %s", e)
            return 1

    else:
        # Polling mode (default)
        return asyncio.run(async_main(args, logger))


if __name__ == "__main__":
    sys.exit(main())
