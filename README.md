# v-flow

> A CLI + Claude skills bundle to automate media backup and processing workflows for videographers.

**Last updated:** 2026-03-05

---

## Quick Start

### For videographers (recommended)

1. Install v-flow and its Claude skills in one step:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/kaungzinye/v-flow/main/install_vflow.sh | bash
   ```

2. Configure storage paths (runs once per machine):

   In a terminal, run:

   ```bash
   v-flow make-config
   ```

   Then edit `~/.vflow_config.yml` to point to your laptop ingest folder, work SSD, and archive drive.

   Alternatively, in Claude Code or Cursor you can say:

   > “Set up v-flow on this machine.”

   and the **v-flow Setup Assistant** skill will guide you through the same wizard.

3. After setup, in Claude Code or Cursor just ask:

   - “Ingest my card and set up a project on my SSD.”
   - “Back up my ingest folder and free up space.”
   - “Show me duplicate clips from the last day.”

The bundled v-flow skills will call the local `v-flow` CLI for you using that config.

### For developers

1. Install the CLI:
   - `pip install vflow-cli` (or run `pip install -e .` from this repo for local development).
2. Configure: `v-flow make-config` and edit `~/.vflow_config.yml`.
3. Explore commands:
   - `v-flow --help` and `v-flow ingest --help`.

---

## Using v-flow with Claude skills

This repo includes a set of Claude-compatible Agent Skills under the `skills/` directory (for ingest, setup, backup, maintenance, and delivery/tagging).

- When you run the installer from Quick Start, those skills are copied into:
  - `~/.claude/skills` for Claude Code.
  - `~/.cursor/skills` for Cursor.
- In Claude / Cursor, the skills:
  - Listen for intents like “ingest my card”, “back up my ingest folder”, “clean up duplicates”, or “archive this export”.
  - Decide which `v-flow` commands to run (`v-flow ingest`, `v-flow backup`, `v-flow list-duplicates`, etc.).
  - Ask you short clarification questions before doing anything destructive.

If you prefer manual setup instead of the installer, you can copy the folders from `skills/` into your tool’s skills directory and follow the same natural-language prompts.

---

## Table of Contents

- [Overview](#overview)
- [The v-flow Workflow](#the-v-flow-workflow)
- [Setup](#setup)
- [Workflow Commands](#workflow-commands)
  - [ingest](#v-flow-ingest)
  - [prep](#v-flow-prep)
  - [pull](#v-flow-pull)
  - [create-select](#v-flow-create-select)
  - [archive](#v-flow-archive)
- [Utility Commands](#utility-commands)
  - [consolidate](#v-flow-consolidate)
  - [copy-meta](#v-flow-copy-meta)
  - [backup](#v-flow-backup)
  - [verify-backup](#v-flow-verify-backup)
  - [list-backups](#v-flow-list-backups)
  - [restore-folder](#v-flow-restore-folder)

---

## Overview

v-flow is designed around a professional media workflow that separates your storage into:

- **Archive** (large HDD) - Long-term storage for all raw footage and final exports
- **Workspace** (fast SSD) - Temporary workspace for active projects

This separation keeps your SSD clean and your media library organized.

---

## The v-flow Workflow

The lifecycle of a project follows these steps:

### 1. **Ingest** → Backup new footage
Copy footage from SD card to both laptop and archive for immediate backup.

### 2. **Prep or Pull** → Move to workspace
- **`prep`** - Move files from laptop ingest folder to work SSD (moves files)
- **`pull`** - Copy files from archive to work SSD (keeps archive intact, perfect for older footage)

### 3. **Edit & Grade** → Create content
Work on your project and create reusable, graded clips.

### 4. **Create Select** → Save graded clips
Tag and save graded clips for future use. Archives to permanent storage and places a copy in your project's selects folder.

### 5. **Archive** → Finalize project
Tag the final export, archive it, and clean up source files from the SSD to free up space.

---

## Setup

### Step 1: Create Configuration File

```bash
v-flow make-config
```

This creates `~/.vflow_config.yml` in your home directory.

### Step 2: Configure Storage Paths

Edit `~/.vflow_config.yml` and update the paths to match your setup:

```yaml
locations:
  laptop: "/path/to/your/laptop/ingest/folder"
  work_ssd: "/path/to/your/fast/ssd/projects"
  archive_hdd: "/path/to/your/archive/hdd"
```

**Important:** You must configure these paths before using v-flow commands.

---

## Workflow Commands

These commands follow the standard v-flow workflow from ingest to archive.

---

### `v-flow ingest`

Safely copies footage from an SD card to two separate locations (laptop and archive) for immediate backup. Supports automatic shoot naming by file date range and safety checks for duplicates.

#### Prerequisites
- Configured `~/.vflow_config.yml` file

#### Options

| Flag | Description |
|------|-------------|
| `--source, -s` | **(required)** Exact folder where videos exist (e.g., `.../M4ROOT/CLIP`) |
| `--shoot, -n` | **(optional if `--auto`)** Shoot folder name, e.g., `2025-10-12_ShootName` or `2025-10-12_to_2025-10-15_ShootName` |
| `--auto, -a` | Infer shoot name from date range of media files. If multiple days detected, uses a range |
| `--force, -f` | Bypass date-range validation warnings when `--shoot` name doesn't match detected file dates |
| `--skip-laptop` | Skip copying files to the laptop ingest folder (saves space) |
| `--workspace, -w` | Also ingest directly to the Workspace SSD (creates project structure) |
| `--split-by-gap` | Automatically split footage into multiple shoots if a time gap of X hours is detected (overrides config default) |

#### Configuration

You can set a default split gap in your `~/.vflow_config.yml`:

```yaml
settings:
  default_split_gap: 24 # Automatically split trips separated by 24+ hours
```

#### Examples

**Standard ingest:**
```bash
v-flow ingest --source "/Volumes/SDCARD/private/M4ROOT/CLIP" --auto
```

**Ingest directly to Workspace (skipping laptop) and split trips:**
```bash
v-flow ingest --source "/Volumes/SDCARD/private/M4ROOT/CLIP" --auto --skip-laptop --workspace --split-by-gap 24
```

#### Behavior
- Recursively finds common video formats (.mp4, .mov, .mxf, .mts, .avi, .m4v)
- Derives date range from file creation/modification dates
- **Smart Splitting:** If `--split-by-gap` is set (or configured), splits footage into separate shoots based on time gaps
- **Storage Fallback:** If a destination drive is full, it skips that drive and continues to the Archive (ensuring backup)
- **Cross-shoot duplicate check:** Skips any file (by name + size) already present anywhere in laptop ingest or archive, not just in the current shoot folder. So if the 28th was already ingested, ingesting 28th+29th will only copy new files from the 29th.
- Detects existing shoots in laptop ingest and archive locations; copies only missing files
- Creates target shoot folders if needed

---

### `v-flow prep`

Prepares a shoot for editing by moving it from the laptop ingest folder to your fast work SSD. Creates a standard project structure.

#### Prerequisites
- Shoot must be in the laptop ingest folder (from `ingest`)

#### Usage
```bash
v-flow prep --shoot <YYYY-MM-DD_ShootName>
```

#### Project Structure Created
```
<shoot_name>/
├── 01_Source/        # Raw footage moved here
├── 02_Resolve/       # DaVinci Resolve project files
├── 03_Exports/       # Your exports go here
├── 04_FinalRenders/  # Final renders
└── 05_Graded_Selects/ # Reusable graded clips
```

#### Note
This **moves** files from ingest to work SSD. If your files are already archived and not in the ingest folder, use `pull` instead.

---

### `v-flow pull`

Pulls files from archive to your work SSD for editing. Copies (doesn't move) files so they remain safely in archive. Perfect for working with archived footage or creating quick edits.

#### Prerequisites
- Shoot must exist in the archive at:
  - `/Video/RAW/[shoot_name]` for raw files
  - `/Video/Graded_Selects/[shoot_name]` for graded selects

#### Options

| Flag | Description |
|------|-------------|
| `--shoot, -n` | **(required)** Name of the shoot to pull from archive |
| `--source, -s` | **(optional, default: `raw`)** What to pull:<br>• `raw` - Pull raw files from `Video/RAW/` → `01_Source/` (default)<br>• `selects` - Pull graded selects from `Video/Graded_Selects/` → `05_Graded_Selects/`<br>• `both` - Pull both raw files and graded selects to their respective folders |
| `--files, -f` | **(optional)** Specific filenames, patterns, or ranges to pull. Can be specified multiple times. Supports ranges like `C3317-C3351` (matches C3317 through C3351). If omitted, pulls all video files |

#### Examples

**Pull all raw files (for full grade):**
```bash
v-flow pull --shoot 2025-10-12_Germany_Trip --source raw
```

**Pull only graded selects (for quick TikTok edit):**
```bash
v-flow pull --shoot 2025-10-12_Germany_Trip --source selects
```

**Pull both raw and graded selects:**
```bash
v-flow pull --shoot 2025-10-12_Germany_Trip --source both
```

**Pull specific files with filter:**
```bash
v-flow pull --shoot 2025-10-12_Germany_Trip --source selects --files "sunset" --files "beach"
```

**Pull a range of files (e.g., C3317 to C3351):**
```bash
v-flow pull --shoot Germany --source raw --files "C3317-C3351"
```

#### Behavior
- Creates standard project structure on work SSD
- Raw files → `01_Source/` folder
- Graded selects → `05_Graded_Selects/` folder
- Files remain in archive (copy operation, not move)
- Skips files that already exist (based on filename and size)
- If a source directory doesn't exist, shows warning and continues with available sources

---

### `v-flow create-select`

Creates a reusable, tagged, graded clip from an export. Archives a copy to `/Video/Graded_Selects/` and places another copy in your active project's `05_Graded_Selects` folder on your SSD for immediate use.

#### Prerequisites
- Project must have been prepped
- Must have an exported video file in the `03_Exports` folder

#### Usage
```bash
v-flow create-select --shoot <YYYY-MM-DD_ShootName> --file <graded_clip.mov> --tags "Graded Select, Tag, Another Tag"
```

#### What Happens
1. Tags the file with metadata (both universal metadata and macOS Finder tags)
2. Copies metadata from original source file if available
3. Archives a copy to `/Video/Graded_Selects/[shoot_name]/` in your archive
4. Places a copy in `05_Graded_Selects/` folder on your work SSD

---

### `v-flow archive`

Archives a final project export. Embeds metadata tags, sends the file to `/Video/Graded/` in your archive, and optionally cleans up source files from the work SSD to save space.

#### Prerequisites
- Project must have been prepped
- Must have a final exported video file in the `03_Exports` folder

#### Usage
```bash
v-flow archive --shoot <YYYY-MM-DD_ShootName> --file <final_export.mp4> --tags "Final, Project, Tag"
```

#### Options

| Flag | Description |
|------|-------------|
| `--shoot, -n` | **(required)** Name of the shoot |
| `--file, -f` | **(required)** Filename of the exported video to archive |
| `--tags, -t` | **(required)** Comma-separated metadata tags |
| `--keep-log` | **(optional)** Do not delete source files from `01_Source/` folder |

#### What Happens
1. Tags the file with metadata
2. Archives to `/Video/Graded/` in your archive
3. Optionally deletes source files from `01_Source/` folder (unless `--keep-log` is used)

---

## Utility Commands

These commands help with maintenance and migration tasks.

---

### `v-flow consolidate`

A utility for migrating legacy media. Finds and copies unique media from an external drive or folder into your archive without creating duplicates. Best used for importing old projects into the v-flow structure.

#### Prerequisites
- Configured `~/.vflow_config.yml` file

#### Usage
```bash
v-flow consolidate --source <path-to-external-folder> --output-folder <NewFolderNameInArchive>
```

#### Behavior
- Builds an index of existing archive files (by name and size)
- Scans source directory and copies only unique files
- Creates log files (`copied_files.txt` and `skipped_duplicates.txt`) in the output folder

---

### `v-flow copy-meta`

Copies metadata (like creation date) from original camera files to final exports by matching filenames in two folders. Useful for preserving original file metadata in your exports.

#### Prerequisites
- `ffmpeg` must be installed
- Source and target folders must contain files with matching filenames (extensions can differ)

#### Usage
```bash
v-flow copy-meta --source-folder <path-to-originals> --target-folder <path-to-exports>
```

#### Behavior
- Matches files by filename stem (ignoring extensions)
- Copies all metadata from source to target using ffmpeg
- Preserves video/audio streams from target file
- Uses stream copy (no re-encoding)

---

### `v-flow backup`

Backs up media from an arbitrary source folder (for example, an ingest folder on your laptop or SSD) into your archive with duplicate checks. This is a friendly wrapper around the `consolidate` logic and is ideal for safely emptying ingest folders after you have already ingested from SD.

#### Prerequisites
- Configured `~/.vflow_config.yml` file

#### Usage
```bash
v-flow backup --source "/Users/you/Desktop/Ingest" --destination "Video/RAW/Desktop_Ingest"
```

#### Options

| Flag | Description |
|------|-------------|
| `--source, -s` | **(required)** Source directory to back up (e.g., your ingest folder) |
| `--destination, -d` | **(required)** Path **relative to the archive root** where files will be copied (e.g., `Video/RAW/Desktop_Ingest`) |
| `--files, -f` | **(optional)** Specific filenames, patterns, or ranges to back up (e.g. `C3317`, `C3317-C3351`, or partial names). Can be specified multiple times |
| `--tags, -t` | **(optional)** Comma-separated metadata tags to add to copied files |
| `--dry-run` | Analyze what would be backed up without copying any files. Shows which files would be copied or skipped as duplicates |
| `--delete-source` | After copying, prompt to optionally delete source files that were successfully backed up |

#### Behavior
- Builds an index of existing archive files (by name and size) so it can skip duplicates that are already in the archive, even if they live in other folders.
- Scans the source directory and copies only unique files into `archive_hdd/<destination>`.
- Creates log files (`copied_files.txt` and `skipped_duplicates.txt`) in the destination folder.
- With `--delete-source`, tracks which files were actually copied and **after the copy completes** offers an interactive prompt to delete those source files.

#### Example: Backup and clean an ingest folder

```bash
# 1) Dry-run to see what would be copied and what could be deleted
v-flow backup \
  --source "/Users/you/Desktop/Ingest" \
  --destination "Video/RAW/Desktop_Ingest" \
  --dry-run \
  --delete-source

# 2) Real backup with interactive delete prompt
v-flow backup \
  --source "/Users/you/Desktop/Ingest" \
  --destination "Video/RAW/Desktop_Ingest" \
  --delete-source
```

---

### `v-flow verify-backup`

Verifies that files in a source folder exist in a destination folder with matching sizes. Can be used directly after `backup` or after any other manual/automated copy to confirm that your backup is complete before deleting source files.

#### Usage

```bash
# Simple path-for-path mirror check
v-flow verify-backup \
  --source "/Users/you/Desktop/Ingest" \
  --destination "/Volumes/Archive/Video/RAW/Desktop_Ingest"

# Archive-wide safety check (recommended for ingest folders)
v-flow verify-backup \
  --source "/Users/you/Desktop/Ingest" \
  --destination "/Volumes/Archive" \
  --archive-wide
```

#### Options

| Flag | Description |
|------|-------------|
| `--source, -s` | **(required)** Source directory to verify |
| `--destination, -d` | **(required)** Destination directory to check against |
| `--archive-wide` | Treat destination as an **archive root** and verify that each source file exists **anywhere under it** by name + size (ignores path differences) |
| `--allow-delete` | After a successful verification, prompt to delete all files under the source folder |

#### Behavior
- Compares all files under the source folder:
  - In **mirror mode** (default), it checks that each file exists at the same relative path under destination with the same size.
  - In **archive-wide mode**, it checks that each file exists **somewhere under the destination tree** with the same filename and size, regardless of exact path.
- Prints a summary (files checked, missing files, size mismatches) and lists a sample of any problems.
- If `--allow-delete` is set and verification **passes with no missing/mismatched files**, offers an interactive prompt to delete the source files.

---

### `v-flow list-backups`

Lists backup folders under a given subpath of your archive, including file counts, total sizes, and last modified times. Useful for quickly seeing what has been consolidated and how large each backup set is.

#### Usage

```bash
v-flow list-backups --subpath "Video/RAW/Desktop_Ingest"
```

#### Options

| Flag | Description |
|------|-------------|
| `--subpath, -p` | **(optional, default: `Video/RAW/Desktop_Ingest`)** Subpath under the archive root to scan for backup folders |

#### Behavior
- Uses the configured `archive_hdd` path from `~/.vflow_config.yml`.
- Looks under `archive_hdd/<subpath>` for immediate subfolders (each treated as a backup set).
- For each backup folder, prints:
  - Folder name
  - Number of files
  - Total size (human-readable)
  - Last modified timestamp (based on newest file inside)
- Sorted so that the most recently modified backups appear first.

---

### `v-flow restore-folder`

Restores (copies) an arbitrary folder tree from one location to another. This is the inverse of `backup` for general folders and can be used to pull a backup folder from your archive back to a workspace path.

#### Usage

```bash
# Dry-run to see what would be restored
v-flow restore-folder \
  --source "/Volumes/Archive/Video/RAW/Desktop_Ingest/2026-01-28_to_2026-01-29_Ingest" \
  --destination "/Users/you/Workspace/Restored_2026-01-28" \
  --dry-run

# Real restore
v-flow restore-folder \
  --source "/Volumes/Archive/Video/RAW/Desktop_Ingest/2026-01-28_to_2026-01-29_Ingest" \
  --destination "/Users/you/Workspace/Restored_2026-01-28"
```

#### Options

| Flag | Description |
|------|-------------|
| `--source, -s` | **(required)** Source folder to restore from (e.g., an archive backup folder) |
| `--destination, -d` | **(required)** Destination folder to restore into (e.g., a workspace or temp folder) |
| `--dry-run` | Simulate the restore without copying any files. Shows what would be copied or overwritten |
| `--overwrite` | Allow overwriting destination files that differ in size. If false (default), such conflicts are reported and skipped |

#### Behavior
- Recreates the directory structure from `source` under `destination`.
- For each file:
  - If the destination file **does not exist**, it is copied.
  - If the destination file exists and has the **same size**, it is skipped.
  - If the destination file exists and has a **different size**:
    - With `--overwrite` **off** (default), the conflict is reported and the file is left unchanged.
    - With `--overwrite` **on**, the destination file is overwritten.
- In `--dry-run` mode, logs which files **would** be copied or overwritten without touching disk.
