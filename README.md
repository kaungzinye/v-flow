# v-flow

> A CLI tool to automate media backup and processing workflows for videographers.

**Last updated:** 2025-10-29

---

## Quick Start

1. Install: `pip install v-flow` (or clone and install locally)
2. Configure: `v-flow make-config` and edit `~/.vflow_config.yml`
3. Get started: `v-flow ingest --help`

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
