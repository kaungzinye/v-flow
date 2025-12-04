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


def cluster_files_by_date(files_with_dates: list[Tuple[any, datetime]], gap_hours: int) -> list[list[any]]:
    """
    Group files into clusters based on a time gap threshold.
    files_with_dates: List of tuples (file_path, file_date)
    gap_hours: Minimum gap in hours to trigger a split
    
    Returns a list of lists, where each inner list contains file paths for one cluster.
    """
    if not files_with_dates:
        return []
        
    # Sort by date
    sorted_files = sorted(files_with_dates, key=lambda x: x[1])
    
    clusters = []
    current_cluster = []
    
    if not sorted_files:
        return []
        
    # Start first cluster
    current_cluster.append(sorted_files[0][0])
    last_date = sorted_files[0][1]

    for i in range(1, len(sorted_files)):
        file_path, file_date = sorted_files[i]
        
        # Calculate difference in hours
        # Ensure we are comparing datetimes
        if isinstance(file_date, date) and not isinstance(file_date, datetime):
             # Fallback if we only have dates (assume midnight)
             file_date = datetime.combine(file_date, datetime.min.time())
        if isinstance(last_date, date) and not isinstance(last_date, datetime):
             last_date = datetime.combine(last_date, datetime.min.time())

        diff = file_date - last_date
        diff_hours = diff.total_seconds() / 3600
        
        if diff_hours >= gap_hours:
            # Gap exceeded, start new cluster
            clusters.append(current_cluster)
            current_cluster = []
        
        current_cluster.append(file_path)
        last_date = file_date
        
    if current_cluster:
        clusters.append(current_cluster)
        
    return clusters
