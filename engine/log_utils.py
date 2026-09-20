"""
log_utils.py - Structured Logging Utilities
Part of the Visual Director and Shorts Engine.
"""

import sys
import logging
import urllib.error
from typing import Optional

logger = logging.getLogger("yt_shorts_engine")


def log_tier_failure(tier_name: str, exc: Exception, context: str = ""):
    """
    Produces one consistent structured log line per tier failure.
    Includes HTTP status codes if the exception is an HTTPError.
    """
    status_code_str = ""
    if isinstance(exc, urllib.error.HTTPError):
        status_code_str = f" | HTTP {exc.code}"
    elif hasattr(exc, "status_code"):
        status_code_str = f" | HTTP {getattr(exc, 'status_code')}"

    ctx_str = f" | Context: {context}" if context else ""
    msg = f"[Tier Failure] {tier_name}{status_code_str} | Error: {exc}{ctx_str}"
    logger.warning(msg)
    print(msg, file=sys.stderr)
