from __future__ import annotations

import sys
from pathlib import Path

from github_scraper.logger import setup_logger
from github_scraper.ui import launch_app


def main() -> None:
    """Main entry point for GitHub Scraper 2026."""
    # Initialize comprehensive logging system
    logger = setup_logger(
        name="github_scraper",
        log_level="INFO",  # Can be changed to DEBUG for verbose logging
        log_to_file=True,
        log_to_console=True
    )
    
    logger.info("=" * 60)
    logger.info("GitHub Scraper 2026 - Application Startup")
    logger.info("=" * 60)
    logger.info("Logging system initialized successfully")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {Path.cwd()}")
    
    try:
        logger.info("Launching application UI...")
        launch_app()
        logger.info("Application closed normally")
    except Exception as exc:
        logger.critical("Application crashed", exc_info=True)
        raise
    finally:
        logger.info("=" * 60)
        logger.info("GitHub Scraper 2026 - Application Shutdown")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()