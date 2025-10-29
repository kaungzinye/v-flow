# v-flow

A CLI tool to automate media backup and processing workflows for videographers.

---

Last updated: 2025-10-29

## The v-flow Workflow

v-flow is designed around a professional media workflow that separates your storage into a long-term **Archive** (on a large HDD) and a temporary **Workspace** (on a fast SSD). This keeps your SSD clean and your media library organized.

The lifecycle of a project looks like this:

1.  **`ingest`**: Copy new footage from an SD card. It's immediately backed up to your archive and your local ingest folder.
2.  **`prep`**: Move a specific shoot from the ingest folder to your fast work SSD. This creates a standardized project structure for editing.
3.  **Edit & Grade**: Work on your project. As you create reusable, graded clips, use the `create-select` command.
4.  **`create-select`**: Tag a graded clip and save it for future use. A copy is sent to the archive for permanent storage, and another is placed in your project's `05_Graded_Selects` folder on your SSD for immediate access.
5.  **`archive`**: When a project is complete, use this command on the final export. It tags the file, sends it to the archive, and cleans up the original source files from your SSD, freeing up space.

---

## Setup

**1. Create the Config File**
Run `v-flow make-config` to create the `~/.vflow_config.yml` file.

**2. Edit the Config File**
You MUST edit the file to point to your actual storage locations (laptop, work SSD, archive HDD).

---

## Commands

### `v-flow ingest`
*   **Purpose:** Safely copies footage from an SD card to two separate locations (laptop and archive) for immediate backup. Now supports automatic shoot naming by file date range and safety checks for duplicates.
*   **Prerequisites:** A configured `~/.vflow_config.yml` file.
*   **Options:**
    - `--source, -s` (required): Exact folder where videos exist (e.g., `.../M4ROOT/CLIP`).
    - `--shoot, -n` (optional if `--auto`): The shoot folder name, e.g., `2025-10-12_ShootName` or `2025-10-12_to_2025-10-15_ShootName`.
    - `--auto, -a`: Infer shoot name from the date range of media files. If multiple days are detected, a range is used.
    - `--force, -f`: Bypass date-range validation warnings when the provided `--shoot` name does not match detected file dates.
*   **Usage:**
    - Manual naming:
      ```bash
      v-flow ingest --source "/Volumes/SDCARD/private/M4ROOT/CLIP" --shoot 2025-10-12_Stockholm_Broll
      ```
    - Automatic naming by file dates:
      ```bash
      v-flow ingest --source "/Volumes/SDCARD/private/M4ROOT/CLIP" --auto
      ```
*   **Behavior:**
    - Recursively finds common video formats (.mp4, .mov, .mxf, .mts, .avi, .m4v).
    - Derives date range from file creation/modification dates.
    - Detects existing shoots in laptop ingest and archive locations; copies only missing files.
    - Creates target shoot folders if needed.

### `v-flow prep`
*   **Purpose:** Prepares a shoot for editing by moving it to your fast work SSD. It creates a standard project structure: `01_Source`, `02_Resolve`, `03_Exports`, `04_FinalRenders`, and `05_Graded_Selects`.
*   **Prerequisites:** The shoot must have been ingested first.
*   **Usage:**
    ```bash
    v-flow prep --shoot <YYYY-MM-DD_ShootName>
    ```

### `v-flow create-select` (New!)
*   **Purpose:** Creates a reusable, tagged, graded clip from an export. It archives a copy to `/Video/Graded_Selects/` and places another copy in your active project's `05_Graded_Selects` folder on your SSD for immediate use.
*   **Prerequisites:** The project must have been prepped, and you must have an exported video file in the `03_Exports` folder.
*   **Usage:**
    ```bash
    v-flow create-select --shoot <YYYY-MM-DD_ShootName> --file <graded_clip.mov> --tags "Graded Select, Tag, Another Tag"
    ```

### `v-flow archive`
*   **Purpose:** Archives a **final project export**. It embeds metadata tags, sends the file to `/Video/Graded/` in your archive, and cleans up the original source file(s) from the work SSD to save space.
*   **Prerequisites:** The project must have been prepped, and you must have a final exported video file in the `03_Exports` folder.
*   **Usage:**
    ```bash
    v-flow archive --shoot <YYYY-MM-DD_ShootName> --file <final_export.mp4> --tags "Final, Project, Tag"
    ```

### `v-flow consolidate`
*   **Purpose:** A utility for migrating legacy media. It finds and copies unique media from an external drive or folder into your archive without creating duplicates. Best used for importing old projects into the v-flow structure.
*   **Prerequisites:** A configured `~/.vflow_config.yml` file.
*   **Usage:**
    ```bash
    v-flow consolidate --source <path-to-external-folder> --output-folder <NewFolderNameInArchive>
    ```

### `v-flow copy-meta`
*   **Purpose:** Copies metadata (like creation date) from original camera files to final exports by matching filenames in two folders.
*   **Prerequisites:** `ffmpeg` must be installed. Source and target folders must contain files with identical names.
*   **Usage:**
    ```bash
    v-flow copy-meta --source-folder <path-to-originals> --target-folder <path-to-exports>
    ```
