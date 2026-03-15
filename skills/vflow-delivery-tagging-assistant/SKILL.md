---
name: vflow-delivery-tagging-assistant
description: Helps users archive final renders, create graded selects, and copy metadata between source and exports. Use when users say things like "archive this export", "make graded selects", or "copy metadata from source to exports".
metadata:
  author: v-flow
  version: 0.1.0
  category: delivery
compatibility: Requires local v-flow CLI, access to v-flow project folders, and permission to read/write exports and archive destinations.
---

# v-flow Delivery & Tagging Assistant

## Purpose and When to Use

Help the user **archive final renders**, **create graded selects**, and **copy metadata** between source and exports.

This skill supports requests like:

- “Archive the final export `Stockholm_v2.mov` with tags ‘clientX, 2025, social’.”
- “Create selects from this export.”
- “Copy metadata from the original camera files to these exports.”

## Clarifying Questions and Defaults

Assumptions:

- v-flow is installed and configured.
- The editing workflow has already produced exports in a shoot’s `03_Exports` folder.
- The agent can:
  - Run local commands: `v-flow archive`, `v-flow create-select`, `v-flow copy-meta`.
  - Ask the user for shoot names, filenames, and tags.

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

- `v-flow archive`
- `v-flow create-select`
- `v-flow copy-meta`

v-flow archive:

```bash
v-flow archive \
  --shoot <shoot_name> \
  --file <export_filename> \
  --tags "<comma,separated,tags>" \
  [--keep-log]
```

Behavior:

- Tags a final exported file.
- Copies it to the archive’s `Video/Graded` folder.
- Optionally cleans up source S-LOG files from `01_Source` if `--keep-log` is **not** set.

v-flow create-select:

```bash
v-flow create-select \
  --shoot <shoot_name> \
  --file <export_filename> \
  --tags "<comma,separated,tags>"
```

Behavior:

- Tags a graded select file.
- Optionally copies metadata from the matching source file in `01_Source`.
- Copies the tagged file to:
  - Archive: `Video/Graded_Selects/<shoot_name>/`
  - Workspace SSD: `<work_ssd>/<shoot_name>/05_Graded_Selects/`

v-flow copy-meta:

```bash
v-flow copy-meta \
  --source-folder <folder_with_originals> \
  --target-folder <folder_with_exports>
```

Behavior:

- Copies metadata from files in `source_folder` to matching stems in `target_folder`.

High-level behavior:

1. Interpret user intent

Map natural language into concrete commands:

- “Archive this final render.”
  - Ask:
    - Which **shoot** is this for?
    - What is the **export filename** in the `03_Exports` folder?
    - Which **tags** should be applied? (Client name, project, year, usage, etc.)
    - Whether they want to keep the original S-LOG sources (`--keep-log`) or clean them up afterwards.
  - Run `v-flow archive` with the gathered parameters.

- “Make selects from this export.”
  - Ask:
    - Which shoot and export file?
    - Which tags should identify this select? (e.g. “b-roll, skyline, 4K”)
  - Run `v-flow create-select`.

- “Copy metadata from source to exports.”
  - Ask for:
    - Source folder (typically `01_Source`).
    - Target folder (e.g. `03_Exports` or another exports directory).
  - Run `v-flow copy-meta`.

Users often refer to files loosely (“the latest export”, “Stockholm final”). When there is ambiguity:

- Offer to:
  - List exports in the shoot’s `03_Exports` folder (names only).
  - Show a small sample of filenames if the folder is large.
- Ask them to pick:
  - Either by exact filename.
  - Or by “most recent export in 03_Exports for this shoot” (in which case you should compute the most recently modified file in that folder).

Tags are provided as a **comma-separated string** to v-flow, but users will describe them in natural language.

When the user says things like:

- “Tags: client X, 2025, social, vertical”

You should:

- Normalize them into a string like:

```text
client X, 2025, social, vertical
```

and pass that as the `--tags` value.

If the user is unsure:

- Suggest a basic structure:
  - Client
  - Project / shoot
  - Year
  - Usage (e.g. “social”, “website”, “broadcast”)

4. Archive vs. selects workflows

Archiving final renders (`v-flow archive`):

- Make clear that this:
  - Archives a final export (e.g. master deliverable).
  - Optionally deletes S-LOG / source files from `01_Source` unless `--keep-log` is set.
- For safety:
  - If the user does **not** mention keeping logs, remind them that S-LOG sources may be cleaned up and ask if that’s intended.
  - If they are unsure, default to `--keep-log` to preserve sources.

Creating graded selects (`v-flow create-select`):

- Explain that this:
  - Archives a graded, reusable clip.
  - Places a copy in the project’s `05_Graded_Selects` folder on the SSD.
- No destructive behavior is involved; it only copies and tags files.

When asked to “copy metadata from source to exports”:

- Confirm:
  - The source folder where original camera files live (`01_Source` typically).
  - The target folder where exports live (`03_Exports` or similar).
- After running `v-flow copy-meta`, summarize:
  - Number of files successfully updated.
  - Number of files skipped due to missing matches.

Examples:

- “Archive the latest export for Stockholm.”
  - Ask:
    - “Which shoot name does Stockholm correspond to in v-flow?”
    - “Should I pick the most recently modified file in `03_Exports` for that shoot?”
    - “What tags should I use?”
  - Resolve to a specific file before calling `v-flow archive`.

- “Make selects from yesterday’s export.”
  - As above, determine shoot + export file precisely.
  - Ask what tags distinguish these selects.

Before running `v-flow archive`:

- [ ] The shoot name is confirmed.
- [ ] The export file (in `03_Exports`) is confirmed.
- [ ] Tags string is constructed and shown to the user.
- [ ] The user has explicitly chosen whether to keep or delete S-LOG sources (`--keep-log`).

Before running `v-flow create-select`:

- [ ] Shoot and export file are unambiguous.
- [ ] Tags are set as the user intends.

Before running `v-flow copy-meta`:

- [ ] Source and target folders are correct and exist.
- [ ] The user understands that existing target files are overwritten **in-place** with new metadata, but their video content is preserved.

## Troubleshooting

- **Export file not found**: List contents of the shoot’s `03_Exports` folder and ask the user to pick a specific filename.
- **ffmpeg or tagging errors**: Surface the error message, suggest installing ffmpeg or checking PATH, then retry.
- **Metadata copy mismatches**: Report which exports had no matching source; suggest verifying naming conventions in `01_Source` and `03_Exports`.


