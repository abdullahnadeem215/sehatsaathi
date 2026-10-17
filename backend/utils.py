"""Utility helpers for time and formatting.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Returns timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Returns ISO 8601 UTC string with trailing 'Z'."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
