"""Shared validation types for domain models."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def normalize_utc(value: datetime) -> datetime:
    """Require a timezone-aware timestamp and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware and expressed in UTC.")
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(normalize_utc)]
