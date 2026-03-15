---
name: vflow-maintenance-assistant
description: Helps users find and safely clean up duplicate media across archive and laptop. Use when users say things like "show me duplicates", "clean up duplicate clips", or "remove duplicates from the last day".
metadata:
  author: v-flow
  version: 0.1.0
  category: maintenance
compatibility: Requires local v-flow CLI, access to archive and laptop ingest folders, and permission to delete duplicate media when confirmed.
---

# v-flow Maintenance Assistant

## Purpose and When to Use

Help the user **find and clean up duplicate media files** across archive and laptop ingest, safely and with clear reporting.

This skill supports intents like:

- “Show me duplicates in my archive.”
- “Remove duplicate clips from the last 24 hours.”
- “Clean up duplicates on both archive and laptop.”

## Clarifying Questions and Defaults

Assumptions:

- v-flow is installed and configured.
- The agent can:
  - Run local commands: `v-flow list-duplicates`, `v-flow remove-duplicates`.
  - Ask for confirmation before destructive operations.

## CLI Availability Check

Before doing anything else, verify the `v-flow` CLI is available:

```bash
which v-flow
```

If the command is not found, install it silently and confirm to the user:

```bash
pip3 install --upgrade vflow-cli
```

Then proceed. Do not ask the user to do this manually.

## Core Workflows

Core commands:

- `v-flow list-duplicates`
- `v-flow remove-duplicates`

v-flow list-duplicates:

```bash
v-flow list-duplicates \
  --location <archive|laptop|both> \
  [--past-hours N]
```

Behaviors:

- Scans either:
  - Archive RAW: `<archive_hdd>/Video/RAW/`
  - Laptop ingest: `<laptop>/`
  - Or both.
- Groups files by (name, size) and prints groups where there is more than one file.
- If `--past-hours` is provided, only considers files modified within that time window.

v-flow remove-duplicates:

```bash
v-flow remove-duplicates \
  [--dry-run] \
  [--past-hours N]
```

Behaviors:

- Looks for duplicates in:
  - Archive RAW (`Video/RAW`).
  - Laptop ingest.
- For each group of duplicates:
  - Keeps one copy (first by sorted path).
  - Removes the others (or prints what it *would* remove in `--dry-run` mode).

High-level behavior:

1. Use list-duplicates for visibility first

For any maintenance request, start with `list-duplicates`:

- Decide scope based on user intent:
  - “in archive” → `--location archive`
  - “on laptop” → `--location laptop`
  - “both” or “everywhere” → `--location both`
- If the user mentions “recent ingests” or a time frame:
  - Use `--past-hours N` (e.g. `24` for the last day).

After running:

- Summarize:
  - Total number of duplicate groups.
  - Total extra copies (i.e. how many files could be removed).
  - Optionally highlight a few sample groups (file name and where duplicates live).

When the user asks you to “remove duplicates” or “clean them up”:

1. **Propose using dry-run first**:
   - Run `v-flow remove-duplicates --dry-run [--past-hours N]`.
   - Summarize:
     - How many files would be removed from archive.
     - How many from laptop ingest.
     - Any errors.

2. **Ask for explicit confirmation**:

> “v-flow would remove X duplicates from archive and Y from laptop. Do you want to proceed and actually delete these duplicate files?”

3. **Only then run the real removal**:
   - Run `v-flow remove-duplicates [--past-hours N]` (without `--dry-run`) **only** after a clear “yes”.

If the user is specifically concerned about recent ingests:

- Prefer using `--past-hours`:
  - Example: `--past-hours 24` for “last 24 hours”.
- Explain that:
  - Only duplicates among files modified within that window will be considered.
  - Older files will be untouched.

Examples:

- “Clean up duplicates.”
  - Ask:
    - “Should I look in the archive, on the laptop, or both?”
    - “Do you want me to limit this to recent files (e.g. last 24 hours), or scan everything?”
  - Then run `list-duplicates` followed by `remove-duplicates --dry-run` and ask before real deletion.

- “Show me duplicate clips from the last day.”
  - Use `list-duplicates --location both --past-hours 24`.
  - Summarize rather than dumping the full raw output.

Before running `v-flow remove-duplicates` **without** `--dry-run`:

- [ ] The user has seen a summary from `list-duplicates` or a `remove-duplicates --dry-run` pass.
- [ ] You have confirmed which locations to affect (archive, laptop, or both).
- [ ] The user explicitly agreed to delete duplicates.

Additional best practices:

- Do not suggest `remove-duplicates` as a first step; prefer `list-duplicates` to build trust.
- If the user seems unsure, recommend starting with a time-limited cleanup (e.g. `--past-hours 24`) or staying in `--dry-run` mode.

## Troubleshooting

- **Scan takes too long**: Narrow the scope with `--location` and/or `--past-hours` to focus on recent ingests or a single storage area.
- **Unexpected files marked as duplicates**: Review the groups reported by `list-duplicates` and adjust time window or locations before running removal.
- **User worried about data loss**: Emphasize dry-run mode, summarize what would be deleted, and avoid running non-dry-run removal unless explicitly requested.


