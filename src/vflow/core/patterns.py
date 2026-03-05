import re
from typing import Optional
from pathlib import Path


def _extract_number_from_filename(filename: str) -> Optional[int]:
    """
    Extract the first numeric sequence from a filename.
    Returns the number as an integer, or None if no number found.
    Handles zero-padding by extracting the numeric value.
    """
    match = re.search(r"(\d+)", filename)
    if match:
        return int(match.group(1))
    return None


def _parse_range_pattern(pattern: str) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Parse a range pattern like "C3317-C3351" or "3317-3351" or "C3317-3351".
    Returns (prefix, start_num, end_num) or (None, None, None) if not a range.
    """
    # Pattern to match ranges like "C3317-C3351" or "3317-3351" or "C3317-3351"
    # The pattern can have a prefix before the first number, and optionally before the second
    pattern_upper = pattern.upper()

    # Try pattern with prefix on both sides: "C3317-C3351"
    range_match = re.match(r"^([A-Za-z]*?)(\d+)-([A-Za-z]*?)(\d+)$", pattern_upper)
    if range_match:
        prefix1 = range_match.group(1) if range_match.group(1) else None
        prefix2 = range_match.group(3) if range_match.group(3) else None

        # Use the prefix from the first number, but require both to match (or both be None)
        if (prefix1 is None and prefix2 is None) or (prefix1 and prefix2 and prefix1 == prefix2):
            prefix = prefix1
            start_num = int(range_match.group(2))
            end_num = int(range_match.group(4))

            if start_num <= end_num:
                return (prefix, start_num, end_num)

    # Try pattern with no prefix: "3317-3351" or with prefix only on first: "C3317-3351"
    # This regex allows digits after the dash, and will capture prefix from first number only
    range_match = re.match(r"^([A-Za-z]*?)(\d+)-(\d+)$", pattern_upper)
    if range_match:
        prefix = range_match.group(1) if range_match.group(1) else None
        start_num = int(range_match.group(2))
        end_num = int(range_match.group(3))

        if start_num <= end_num:
            return (prefix, start_num, end_num)

    return (None, None, None)  # Not a range


def _matches_pattern(pattern: str, filename: str) -> bool:
    """
    Check if a filename matches a pattern, handling both regular patterns and ranges.
    Uses numeric comparison to handle zero-padding.
    """
    filename_lower = filename.lower()
    pattern_lower = pattern.lower()

    # First, check if pattern is a range
    prefix, start_num, end_num = _parse_range_pattern(pattern)
    if start_num is not None and end_num is not None:
        # It's a range - extract number from filename and check if in range
        file_num = _extract_number_from_filename(filename)
        if file_num is None:
            return False

        # If prefix specified, check that filename contains the prefix
        if prefix:
            if prefix.lower() not in filename_lower:
                return False

        # Check if number is in range
        return start_num <= file_num <= end_num

    # Not a range - try numeric matching first (for better zero-padding handling)
    pattern_num = _extract_number_from_filename(pattern)
    file_num = _extract_number_from_filename(filename)

    if pattern_num is not None and file_num is not None:
        # Both have numbers - compare numerically and check prefix
        if pattern_num == file_num:
            # Numbers match - check if prefixes match (if pattern has a prefix)
            pattern_letters = re.sub(r"\d+", "", pattern_lower)
            if pattern_letters:
                # Pattern has letters - check if filename contains them
                return pattern_letters in filename_lower
            else:
                # Just a number pattern - match if filename contains this number
                return True

    # Fallback to substring matching for non-numeric patterns
    return pattern_lower in filename_lower

