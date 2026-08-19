from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple


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
