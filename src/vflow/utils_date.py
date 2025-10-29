"""
Date parsing and shoot range helper functions.
"""
from datetime import datetime, date
import re
from typing import Optional, Tuple

def parse_shoot_date_range(shoot_name: str) -> Optional[Tuple[date, date]]:
    """
    Parse a shoot name to extract date range.
    Returns (start_date, end_date) or None if no date found.
    
    Supports formats:
    - YYYY-MM-DD_ShootName (single date)
    - YYYY-MM-DD_to_YYYY-MM-DD_ShootName (date range)
    """
    # Pattern for date range: YYYY-MM-DD_to_YYYY-MM-DD_ShootName
    range_pattern = r'^(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})_(.+)$'
    match = re.match(range_pattern, shoot_name)
    if match:
        try:
            start = datetime.strptime(match.group(1), '%Y-%m-%d').date()
            end = datetime.strptime(match.group(2), '%Y-%m-%d').date()
            return (start, end)
        except ValueError:
            pass
    
    # Pattern for single date: YYYY-MM-DD_ShootName
    single_pattern = r'^(\d{4}-\d{2}-\d{2})_(.+)$'
    match = re.match(single_pattern, shoot_name)
    if match:
        try:
            shoot_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
            return (shoot_date, shoot_date)
        except ValueError:
            pass
    
    return None

def format_shoot_name(start_date: date, end_date: date, name_suffix: str = "Ingest") -> str:
    """
    Format a shoot name from a date range.
    If start and end are the same, use single date format.
    """
    if start_date == end_date:
        return f"{start_date.strftime('%Y-%m-%d')}_{name_suffix}"
    else:
        return f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}_{name_suffix}"

def date_in_range(check_date: date, start_date: date, end_date: date) -> bool:
    """Check if a date falls within a date range (inclusive)."""
    return start_date <= check_date <= end_date

