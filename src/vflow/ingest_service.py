from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from .core.date_utils import (
    DateRange,
    format_date_range,
    format_shoot_name,
    manifest_date_range,
    media_datetime,
    parse_shoot_date_range,
    ranges_overlap,
)
from .core.patterns import _extract_number_from_filename, _matches_pattern
from .card_ingest import holds_footage, ingest_card
from .collection_ingest import holds_photos, ingest_photos
from .prompts import confirm as confirm_decision
from .shoot_manifest import (
    Layout,
    PENDING_MANIFEST_NAME,
    MANIFEST_NAME,
    PHOTO_EXTENSIONS,
    iter_raw_folders,
    raw_root,
    read_manifest,
)


def _get_media_date(file_path: Path) -> datetime:
    """The capture date/time of one media file."""
    return media_datetime(file_path)


def _folder_range(directory: Path) -> Optional[DateRange]:
    """The date range a folder answers for: its manifest's, else the one its name states.

    A manifested folder speaks only through its manifest, so a folder indexed before
    v-flow recorded ranges stays unmatched until `v-flow index` runs again.
    """
    for name in (PENDING_MANIFEST_NAME, MANIFEST_NAME):
        manifest = read_manifest(directory / name)
        if manifest is not None:
            return manifest_date_range(manifest)
    return parse_shoot_date_range(directory.name)


def overlapping_folders(
    archive: Path, kind: str, span: DateRange, layout: Optional[Layout] = None
) -> list[tuple[str, DateRange]]:
    """Existing folders of one media kind whose date range meets the incoming files."""
    found = []
    for directory in iter_raw_folders(archive, kind, layout):
        recorded = _folder_range(directory)
        if recorded is not None and ranges_overlap(recorded, span):
            found.append((directory.name, recorded))
    return found


# The word that scopes one merge answer to one media kind, for the card that raises a
# suggestion for its footage and its photos at once.
MERGE_SCOPES = {"shoot": "video", "collection": "photo"}
MERGE_LABELS = {"video": "Shoot", "photo": "Collection"}


class MergeDecision:
    """The answers --merge-into and --no-merge carry into a run's date-overlap suggestions.

    A bare `--merge-into <name>` answers whichever kind suggests; a card that suggests
    for both kinds needs `shoot=<name>` or `collection=<name>`, so one answer never
    silently lands photos in a Shoot's name or the reverse.
    """

    def __init__(self, merge_into: Optional[list[str]] = None, no_merge: bool = False) -> None:
        self.decline = no_merge
        self.scoped: dict[str, str] = {}
        self.bare: Optional[str] = None
        self.given: set[str] = set()
        self.used: set[str] = set()
        for value in merge_into or []:
            scope, separator, name = value.partition("=")
            if separator and scope in MERGE_SCOPES:
                if not name:
                    raise ValueError(f"--merge-into '{value}' names no {scope}.")
                kind = MERGE_SCOPES[scope]
                if kind in self.scoped:
                    raise ValueError(f"--merge-into names a {scope} twice.")
                self.scoped[kind] = name
            elif self.bare is not None:
                raise ValueError(
                    "--merge-into answers one suggestion; scope each one as "
                    "'shoot=<name>' or 'collection=<name>' to answer both."
                )
            else:
                self.bare = value
            self.given.add(value)
        if self.bare is not None and self.scoped:
            raise ValueError(
                "Give --merge-into as one bare name or as scoped values, not both."
            )

    def answer(self, kind: str, candidate: str, contested: bool) -> Optional[bool]:
        """The flagged answer for one kind's suggestion, or nothing when the flags are silent."""
        name = self.scoped.get(kind)
        given = None if name is None else f"{_scope_word(kind)}={name}"
        if name is None and self.bare is not None:
            if contested:
                raise ValueError(
                    f"A Shoot and a Collection both overlap these files, so "
                    f"--merge-into '{self.bare}' is ambiguous. Pass "
                    f"--merge-into 'shoot=<name>' and --merge-into 'collection=<name>'."
                )
            name = given = self.bare
        if name is None:
            return False if self.decline else None
        self.used.add(given)
        if name != candidate:
            raise ValueError(
                f"No {MERGE_LABELS[kind]} named '{name}' overlaps these files; "
                f"'{candidate}' does."
            )
        return True

    def unanswered(self) -> list[str]:
        """The --merge-into values no suggestion in this run matched."""
        return sorted(self.given - self.used)


def _scope_word(kind: str) -> str:
    return "shoot" if kind == "video" else "collection"


def merge_candidates(
    archive: Path,
    kind: str,
    span: DateRange,
    derived: str,
    layout: Optional[Layout] = None,
) -> list[tuple[str, DateRange]]:
    """Existing folders of one kind that the incoming files could join instead."""
    return [
        (name, recorded)
        for name, recorded in overlapping_folders(archive, kind, span, layout)
        if name != derived
    ]


def _report_ambiguous(kind: str, candidates: list[tuple[str, DateRange]], derived: str, span: DateRange) -> None:
    """List several overlapping folders and choose none of them."""
    label = MERGE_LABELS[kind]
    typer.echo(
        f"These {label}s overlap {format_date_range(span)}, "
        f"so v-flow chooses none of them:"
    )
    for name, recorded in candidates:
        typer.echo(f"  {name} ({format_date_range(recorded)})")
    typer.echo(f"Using {label} '{derived}'. Name one with the matching option to merge.")


def resolve_merges(
    plans: dict[str, dict], decision: MergeDecision, span: Optional[DateRange]
) -> dict[str, str]:
    """Settle every date-overlap suggestion this ingest raises, by flag or by asking.

    One candidate is a question; several are ambiguous, so v-flow lists them and asks
    nothing. Declining, like ambiguity, means the derived name.
    """
    chosen = {kind: plan["derived"] for kind, plan in plans.items()}
    asked = {
        kind: plan["candidates"][0]
        for kind, plan in plans.items()
        if len(plan["candidates"]) == 1
    }
    for kind, plan in plans.items():
        if len(plan["candidates"]) > 1:
            _report_ambiguous(kind, plan["candidates"], plan["derived"], span)

    contested = len(asked) > 1
    for kind, (name, recorded) in asked.items():
        label = MERGE_LABELS[kind]
        derived = plans[kind]["derived"]
        question = (
            f"{label} '{name}' ({format_date_range(recorded)}) overlaps these files "
            f"({format_date_range(span)})."
        )
        answer = decision.answer(kind, name, contested)
        if answer is None:
            flag_value = f"{_scope_word(kind)}={name}" if contested else name
            answer = confirm_decision(
                f"{question} Add them to it instead of a new {label} '{derived}'?",
                question,
                f"--merge-into '{flag_value}' or --no-merge",
            )
        if answer:
            chosen[kind] = name

    unanswered = decision.unanswered()
    if unanswered:
        listed = ", ".join(f"'{value}'" for value in unanswered)
        raise ValueError(
            f"--merge-into {listed} names no folder that overlaps these files."
        )
    return chosen


def ingest_report(
    source_dir: str,
    archive_path: Path,
    laptop_path: Optional[Path] = None,
    priority_day: Optional[int] = None,
    priority_month: Optional[int] = None,
    layout: Optional[Layout] = None,
) -> None:
    """
    Scans SD card (or source) for video files, compares against BOTH laptop ingest
    and archive, and reports what has not been ingested. A file is considered
    ingested if it exists (same name and size) in either destination.
    Optionally highlights a priority date (e.g. 28th).
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    video_extensions = {
        ".mp4",
        ".mov",
        ".mxf",
        ".mts",
        ".avi",
        ".m4v",
        ".braw",
        ".r3d",
        ".crm",
    }
    all_files: list[Path] = []
    for file_path in source_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No video files found in the source directory.", err=True)
        return

    laptop_index: set[tuple[str, int]] = set()
    if laptop_path and laptop_path.exists():
        for f in laptop_path.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    laptop_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    archive_raw = raw_root(archive_path, "video", layout)
    archive_index: set[tuple[str, int]] = set()
    if archive_raw.exists():
        for f in archive_raw.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    archive_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    from collections import defaultdict

    by_date: dict[date, list[tuple[Path, int, bool, bool]]] = defaultdict(list)
    for f in all_files:
        try:
            dt = _get_media_date(f)
            d = dt.date()
            size = f.stat().st_size
            key = (f.name, size)
            in_laptop = key in laptop_index
            in_archive = key in archive_index
            by_date[d].append((f, size, in_laptop, in_archive))
        except (OSError, FileNotFoundError):
            continue

    dates_sorted = sorted(by_date.keys())

    typer.echo("\n" + "=" * 70)
    typer.echo("INGEST REPORT (SD CARD = SOURCE OF TRUTH)")
    typer.echo("=" * 70)
    typer.echo(f"SD card: {source_path}")
    typer.echo(f"Laptop:  {laptop_path}")
    typer.echo(f"Archive: {archive_raw}")
    typer.echo(
        f"Total on SD: {len(all_files)}  |  Laptop index: {len(laptop_index)}  |  Archive index: {len(archive_index)}"
    )
    typer.echo("=" * 70)

    not_on_laptop_by_date: dict[date, list] = {}
    not_on_archive_by_date: dict[date, list] = {}
    for d in dates_sorted:
        items = by_date[d]
        on_laptop = sum(1 for _, _, lb, _ in items if lb)
        on_archive = sum(1 for _, _, _, ab in items if ab)
        missing_laptop = [x for x in items if not x[2]]
        missing_archive = [x for x in items if not x[3]]
        not_on_laptop_by_date[d] = missing_laptop
        not_on_archive_by_date[d] = missing_archive
        priority_mark = ""
        if priority_day is not None and d.day == priority_day:
            if priority_month is None or d.month == priority_month:
                priority_mark = "  << PRIORITY"
        typer.echo(
            f"\n{d}  on SD: {len(items)}  |  laptop: {on_laptop}/{len(items)}  |  archive: {on_archive}/{len(items)}{priority_mark}"
        )
        if missing_laptop:
            names = sorted(x[0].name for x in missing_laptop)
            typer.echo(
                "   Missing from laptop:  "
                + (
                    ", ".join(names)
                    if len(names) <= 10
                    else f"{names[0]} .. {names[-1]} ({len(names)} files)"
                )
            )
        if missing_archive:
            names = sorted(x[0].name for x in missing_archive)
            typer.echo(
                "   Missing from archive: "
                + (
                    ", ".join(names)
                    if len(names) <= 10
                    else f"{names[0]} .. {names[-1]} ({len(names)} files)"
                )
            )

    on_both = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and ab
    )
    laptop_only_from_sd = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and not ab
    )
    archive_only_from_sd = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if ab and not lb
    )
    on_neither = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if not lb and not ab
    )

    typer.echo("\n" + "=" * 70)
    typer.echo("SUMMARY (files on SD card)")
    typer.echo("=" * 70)
    typer.echo(f"  On both laptop + archive: {on_both}")
    typer.echo(f"  On laptop only:           {laptop_only_from_sd}")
    typer.echo(f"  On archive only:          {archive_only_from_sd}")
    typer.echo(f"  On neither (not ingested): {on_neither}")
    typer.echo("=" * 70)

    if on_neither > 0:
        typer.echo("\nSUGGESTED INGEST (missing from both):")
        for d in dates_sorted:
            not_ing = [x for x in by_date[d] if not x[2] and not x[3]]
            if not not_ing:
                continue
            names = sorted(x[0].name for x in not_ing)
            nums = [_extract_number_from_filename(n) for n in names]
            nums = [n for n in nums if n is not None]
            if nums:
                typer.echo(
                    f"  {d}:  --files C{min(nums)}-C{max(nums)}  ({len(not_ing)} files)"
                )
    typer.echo("")


def _abort(error: Exception) -> typer.Exit:
    typer.echo(f"Ingest failed: {error}", err=True)
    typer.echo(
        "Verified Archive files remain intact; retry the same ingest to resume.",
        err=True,
    )
    return typer.Exit(code=1)


def _summarize(result: dict, kind: str) -> None:
    typer.echo(
        f"Import Batch '{result['batch_id']}': "
        f"{result['copied']} copied, {result['verified']} already verified, "
        f"{result['deduplicated']} deduplicated, {result['excluded']} excluded, "
        f"{result['files']} in {kind}."
    )
    typer.echo(f"Manifest: {result['manifest_path']}")


def ingest_media(
    source_dir: str,
    shoot_name: str,
    archive_dest: Path,
    auto: bool = False,
    collection_name: Optional[str] = None,
    files_filter: Optional[list[str]] = None,
    import_batch_id: Optional[str] = None,
    include_all: bool = False,
    layout: Optional[Layout] = None,
    merge_into: Optional[list[str]] = None,
    no_merge: bool = False,
) -> None:
    """Copy one card's footage into a flat Shoot and its photos into a flat Collection."""
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    all_source_files = [path for path in source_path.rglob("*") if path.is_file()]
    selected_files: Optional[list[Path]] = None
    if files_filter:
        selected_files = []
        for pattern in files_filter:
            selected_files.extend(
                path for path in all_source_files if _matches_pattern(pattern, path.name)
            )
        selected_files = list(dict.fromkeys(selected_files))
        if not selected_files:
            typer.echo(
                f"No files found matching filter: {', '.join(files_filter)}",
                err=True,
            )
            raise typer.Exit(code=1)

    files_for_identity = selected_files if selected_files is not None else all_source_files
    if not files_for_identity:
        typer.echo("No files found in the source directory.", err=True)
        raise typer.Exit(code=1)

    span: Optional[DateRange] = None
    target_shoot_name = shoot_name
    if auto:
        dates = [_get_media_date(path) for path in files_for_identity]
        span = (min(dates).date(), max(dates).date())
        target_shoot_name = format_shoot_name(span[0], span[1], "Ingest")
    if not target_shoot_name:
        typer.echo("Shoot name is required when --auto is not used.", err=True)
        raise typer.Exit(code=1)

    footage = holds_footage(source_path, files_for_identity)
    photos = holds_photos(source_path, files_for_identity)
    if not footage and not photos:
        typer.echo("No footage or photos found in the source directory.", err=True)
        raise typer.Exit(code=1)

    # The Collection carries the Shoot's name so one card lands under one identity.
    target_collection_name = collection_name or target_shoot_name

    # A name given on the command line is the decision, so only --auto asks.
    plans: dict[str, dict] = {}
    if span is not None and footage:
        plans["video"] = {
            "derived": target_shoot_name,
            "candidates": merge_candidates(
                archive_dest, "video", span, target_shoot_name, layout
            ),
        }
    if span is not None and photos and not collection_name:
        plans["photo"] = {
            "derived": target_collection_name,
            "candidates": merge_candidates(
                archive_dest, "photo", span, target_collection_name, layout
            ),
        }
    try:
        decision = MergeDecision(merge_into, no_merge)
        chosen = resolve_merges(plans, decision, span)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    target_shoot_name = chosen.get("video", target_shoot_name)
    target_collection_name = chosen.get("photo", target_collection_name)

    if footage:
        typer.echo(f"Archiving footage into Shoot '{target_shoot_name}'...")
        try:
            result = ingest_card(
                source=source_path,
                archive=archive_dest,
                shoot=target_shoot_name,
                batch_id=import_batch_id,
                selected_files=selected_files,
                include_all=include_all,
                layout=layout,
            )
        except (OSError, ValueError) as error:
            raise _abort(error)
        typer.echo(f"Shoot folder: {result['shoot_directory']}")
        _summarize(result, "Shoot")

    if photos:
        typer.echo(f"Archiving photos into Collection '{target_collection_name}'...")
        try:
            result = ingest_photos(
                source=source_path,
                archive=archive_dest,
                collection=target_collection_name,
                batch_id=import_batch_id,
                selected_files=selected_files,
                layout=layout,
            )
        except (OSError, ValueError) as error:
            raise _abort(error)
        typer.echo(f"Collection folder: {result['collection_directory']}")
        _summarize(result, "Collection")

    typer.echo("Retained copies: 1 (Archive only). The source remains untouched.")


def card_report(
    source_dir: str,
    archive_path: Path,
    layout: Optional[Layout] = None,
) -> None:
    """
    Reports what's on a card. Auto-detects video (private/M4ROOT/CLIP) and photo
    (DCIM/100MSDCF) folders, groups files by date, and shows first/last filename,
    count, and whether videos are already in the archive.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    video_folder = source_path / "private" / "M4ROOT" / "CLIP"
    photo_folder = source_path / "DCIM" / "100MSDCF"

    video_extensions = {".mp4", ".mov", ".mxf", ".mts", ".avi", ".m4v", ".braw", ".r3d", ".crm"}
    photo_extensions = PHOTO_EXTENSIONS

    typer.echo("\n" + "=" * 70)
    typer.echo("CARD REPORT")
    typer.echo("=" * 70)
    typer.echo(f"Card: {source_path}")

    # Build archive-wide video index for presence check
    archive_video_raw = raw_root(archive_path, "video", layout)
    archive_video_index: set[tuple[str, int]] = set()
    if archive_video_raw.exists():
        for f in archive_video_raw.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    archive_video_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    from collections import defaultdict

    # VIDEO SECTION
    if video_folder.exists() and video_folder.is_dir():
        video_files: list[Path] = []
        for f in video_folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                video_files.append(f)

        typer.echo(f"\nVIDEOS  ({video_folder})")
        typer.echo("-" * 70)

        if not video_files:
            typer.echo("  No video files found.")
        else:
            by_date: dict = defaultdict(list)
            for f in video_files:
                try:
                    d = _get_media_date(f).date()
                    by_date[d].append(f)
                except Exception:
                    continue

            for d in sorted(by_date.keys()):
                day_files = sorted(by_date[d], key=lambda f: f.name)
                count = len(day_files)
                first = day_files[0].name
                last = day_files[-1].name
                on_archive = sum(
                    1 for f in day_files
                    if (f.name, f.stat().st_size) in archive_video_index
                )
                hdd_label = f"{on_archive}/{count} on HDD" if on_archive > 0 else "NOT on HDD"
                if first == last:
                    typer.echo(f"  {d}  {count} file(s)  [{first}]  {hdd_label}")
                else:
                    typer.echo(f"  {d}  {count} file(s)  [{first} .. {last}]  {hdd_label}")
    else:
        typer.echo(f"\nVIDEOS  — folder not found ({video_folder})")

    # PHOTO SECTION
    if photo_folder.exists() and photo_folder.is_dir():
        photo_files: list[Path] = []
        for f in photo_folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in photo_extensions:
                photo_files.append(f)

        typer.echo(f"\nPHOTOS  ({photo_folder})")
        typer.echo("-" * 70)

        if not photo_files:
            typer.echo("  No RAW photo files found.")
        else:
            by_date_p: dict = defaultdict(list)
            for f in photo_files:
                try:
                    d = _get_media_date(f).date()
                    by_date_p[d].append(f)
                except Exception:
                    continue

            for d in sorted(by_date_p.keys()):
                day_files = sorted(by_date_p[d], key=lambda f: f.name)
                count = len(day_files)
                first = day_files[0].name
                last = day_files[-1].name
                if first == last:
                    typer.echo(f"  {d}  {count} file(s)  [{first}]")
                else:
                    typer.echo(f"  {d}  {count} file(s)  [{first} .. {last}]")
    else:
        typer.echo(f"\nPHOTOS  — folder not found ({photo_folder})")

    typer.echo("\n" + "=" * 70 + "\n")
