from __future__ import annotations

import time
from typing import Callable, Optional

import typer

from .core.fs_ops import _format_bytes


# How often a long run says where it has got to, and the file size that earns
# updates from inside one file rather than only when it finishes.
INTERVAL_SECONDS = 3.0
LARGE_FILE_BYTES = 256 * 1024 * 1024


class Progress:
    """Plain progress lines for one long transfer.

    Lines carry files done of total, bytes done of total, and the file in hand. They
    are ordinary text with no control characters, so an agent capturing the output
    reads the same thing a person watching a terminal does, and they are throttled so
    a fast run stays quiet.
    """

    def __init__(
        self,
        verb: str,
        files: int,
        byte_total: int,
        clock: Callable[[], float] = time.monotonic,
        emit: Callable[[str], None] = typer.echo,
    ) -> None:
        self.verb = verb
        self.files = files
        self.byte_total = byte_total
        self._clock = clock
        self._emit = emit
        self._done_files = 0
        self._done_bytes = 0
        self._current = ""
        self._current_bytes = 0
        self._last: Optional[float] = None

    def resuming(self, settled: int, total: int, state: str = "verified") -> None:
        """Say what the manifest already covers, before one file is read."""
        if settled:
            self._emit(f"{settled} of {total} files {state}; resuming.")

    def start(self, name: str, byte_size: int) -> None:
        """Begin one file and offer a line about it."""
        self._current = name
        self._current_bytes = 0
        self._line()

    def advance(self, byte_count: int) -> None:
        """Report bytes landing inside the file in hand."""
        self._current_bytes += byte_count
        self._done_bytes += byte_count
        self._line()

    def settled(self, byte_size: int) -> None:
        """Close one file out, counting whatever was not reported chunk by chunk."""
        self._done_files += 1
        self._done_bytes += byte_size - self._current_bytes
        self._current_bytes = byte_size

    def within_file(self, byte_size: int) -> Optional[Callable[[int], None]]:
        """A per-chunk reporter for a file big enough to earn updates from inside."""
        return self.advance if byte_size >= LARGE_FILE_BYTES else None

    def _line(self) -> None:
        now = self._clock()
        if self._last is not None and now - self._last < INTERVAL_SECONDS:
            return
        self._last = now
        self._emit(
            f"{self.verb} {min(self._done_files + 1, self.files)}/{self.files} files, "
            f"{_format_bytes(self._done_bytes)}/{_format_bytes(self.byte_total)}: "
            f"{self._current}"
        )
