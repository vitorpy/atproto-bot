"""Main entry point for the ATproto bot."""

import argparse
import asyncio
import logging
import sys

from .bot import Bot
from .config import load_config
from .services import get_db_service, init_db_service


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


async def async_main(args, logger) -> int:
    """Async main function."""
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
  %(prog)s                      # Run with default config.yaml
  %(prog)s -c myconfig.yaml     # Run with custom config
  %(prog)s -v                   # Run with verbose logging
  %(prog)s --once               # Process once and exit (useful for testing)
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

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    return asyncio.run(async_main(args, logger))


if __name__ == "__main__":
    sys.exit(main())
