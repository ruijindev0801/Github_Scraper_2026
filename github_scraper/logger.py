"""
Comprehensive logging system for GitHub Scraper 2026.

This module provides centralized logging with multiple handlers, structured formatting,
and contextual information for debugging and monitoring.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class SensitiveDataFilter(logging.Filter):
 """Filter to mask sensitive data like tokens and API keys in logs."""
 
 def filter(self, record: logging.LogRecord) -> bool:
 """Mask sensitive information in log messages."""
 if isinstance(record.msg, str):
 # Mask GitHub tokens (ghp_, github_pat_, etc.)
 import re
         record.msg = re.sub(
             r'(gh[ps]_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})',
             '[GITHUB_TOKEN_REDACTED]',
             record.msg
         )
         # Mask Google service account keys
         record.msg = re.sub(
             r'("private_key_id":\s*")[^"]+("|"private_key":\s*")[^"]+"',
             r'\1[SERVICE_ACCOUNT_KEY_REDACTED]\2',
             record.msg
         )
     return True


def setup_logger(
    name: str = "github_scraper",
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_log_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Set up a comprehensive logger with multiple handlers.
    
    Args:
        name: Logger name
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console
        max_log_size: Maximum size of each log file
        backup_count: Number of backup log files to keep
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Prevent duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(simple_formatter)
        console_handler.addFilter(sensitive_filter)
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_to_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Create timestamped log file name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f"github_scraper_{timestamp}.log"
        
        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_log_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        file_handler.setFormatter(detailed_formatter)
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)
        
        # Also log to a persistent file that accumulates all logs
        persistent_log = log_dir / "github_scraper_persistent.log"
        persistent_handler = logging.handlers.RotatingFileHandler(
            persistent_log,
            maxBytes=max_log_size * 2,  # Larger size for persistent log
            backupCount=backup_count,
            encoding='utf-8'
        )
        persistent_handler.setLevel(logging.INFO)
        persistent_handler.setFormatter(detailed_formatter)
        persistent_handler.addFilter(sensitive_filter)
        logger.addHandler(persistent_handler)
    
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance. If no name provided, returns root logger.
    
    Args:
        name: Optional logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"github_scraper.{name}")
    return logging.getLogger("github_scraper")


class LogContext:
    """Context manager for adding contextual information to logs."""
    
    def __init__(self, **context: Any):
        self.context = context
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def update(self, **kwargs: Any):
        """Update context with additional information."""
        self.context.update(kwargs)
    
    def get_context_str(self) -> str:
        """Get context as a formatted string."""
        if not self.context:
            return ""
        return " | ".join(f"{k}={v}" for k, v in self.context.items())


def log_with_context(logger: logging.Logger, level: int, msg: str, **context: Any):
    """
    Log a message with additional contextual information.
    
    Args:
        logger: Logger instance
        level: Log level
        msg: Log message
        **context: Additional context key-value pairs
    """
    if context:
        context_str = " | ".join(f"{k}={v}" for k, v in context.items())
        msg = f"{msg} | {context_str}"
    logger.log(level, msg)


# Global logger instance
default_logger = setup_logger()


__all__ = [
    'setup_logger',
    'get_logger',
    'LogContext',
    'log_with_context',
    'default_logger',
]