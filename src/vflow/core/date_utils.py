from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

# Where a manifest records the capture-date span of the folder it describes.
MEDIA_DATES_KEY = "media_dates"

DateRange = Tuple[date, date]


def parse_shoot_date_range(shoot_name: str) -> Optional[Tuple[date, date]]:
    """
    Parse a folder name into its date range.
    Returns (start_date, end_date) or None if the name carries no date.

    Supports YYYY-MM-DD_Name and YYYY-MM-DD_to_YYYY-MM-DD_Name.
    """
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})_(.+)$", shoot_name)
    if match:
        try:
            start = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            end = datetime.strptime(match.group(2), "%Y-%m-%d").date()
            return (start, end)
        except ValueError:
            pass

    match = re.match(r"^(\d{4}-\d{2}-\d{2})_(.+)$", shoot_name)
    if match:
        try:
            shoot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            return (shoot_date, shoot_date)
        except ValueError:
            pass

    return None


def format_shoot_name(
    start_date: date, end_date: date, name_suffix: str = "Ingest"
) -> str:
    """
    Format a shoot name from a date range.
    If start and end are the same, use single date format.
    """
    if start_date == end_date:
        return f"{start_date.strftime('%Y-%m-%d')}_{name_suffix}"
    else:
        return (
            f"{start_date.strftime('%Y-%m-%d')}_to_"
            f"{end_date.strftime('%Y-%m-%d')}_{name_suffix}"
        )


def media_datetime(file_path: Path) -> datetime:
    """
    Extract the date/time from a media file.
    Uses filesystem creation date (birthtime) if available, else modification time.
    """
    try:
        stat = file_path.stat()
        creation_time = getattr(stat, "st_birthtime", None)
        if creation_time:
            return datetime.fromtimestamp(creation_time)
        return datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        return datetime.now()


def media_date(file_path: Path) -> date:
    """The capture day of one media file."""
    return media_datetime(file_path).date()


def _parse_date(text: object) -> Optional[date]:
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def manifest_date_range(manifest: dict) -> Optional[DateRange]:
    """The capture-date span a manifest records, or None when it records none."""
    recorded = manifest.get(MEDIA_DATES_KEY)
    if not isinstance(recorded, dict):
        return None
    start = _parse_date(recorded.get("start"))
    end = _parse_date(recorded.get("end"))
    if start is None or end is None or start > end:
        return None
    return (start, end)


def record_media_dates(manifest: dict, dates: Iterable[date]) -> Optional[DateRange]:
    """Grow a manifest's recorded span to cover the given capture dates."""
    days = sorted(dates)
    known = manifest_date_range(manifest)
    if not days:
        return known
    start, end = days[0], days[-1]
    if known is not None:
        start, end = min(start, known[0]), max(end, known[1])
    manifest[MEDIA_DATES_KEY] = {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }
    return (start, end)


def ranges_overlap(left: DateRange, right: DateRange) -> bool:
    """Whether two inclusive date ranges share at least one day."""
    return left[0] <= right[1] and right[0] <= left[1]


def format_date_range(span: DateRange) -> str:
    """One date range as a person reads it."""
    start, end = span
    if start == end:
        return start.strftime("%Y-%m-%d")
    return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
