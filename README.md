# v-flow

A CLI tool to automate media backup and processing workflows for videographers.

---

## Setup

**1. Create the Config File**
Run `v-flow make-config` to create the `~/.vflow_config.yml` file.

**2. Edit the Config File**
You MUST edit the file to point to your actual storage locations (laptop, work SSD, archive HDD).

---

## Commands

### `v-flow ingest`
*   **Purpose:** Safely copies footage from an SD card to two separate locations for immediate backup.
*   **Prerequisites:** A configured `~/.vflow_config.yml` file.
*   **Usage:**
    ```bash
    v-flow ingest --source <path-to-sd-card> --shoot <YYYY-MM-DD_ShootName>
    ```

### `v-flow prep`
*   **Purpose:** Prepares a shoot for editing by moving it to your fast work SSD and creating a standard project structure.
*   **Prerequisites:** The shoot must have been ingested first.
*   **Usage:**
    ```bash
    v-flow prep --shoot <YYYY-MM-DD_ShootName>
    ```

### `v-flow archive`
*   **Purpose:** Archives a final exported video, embeds metadata tags, and cleans up the original source file from the work SSD.
*   **Prerequisites:** The project must have been prepped, and you must have an exported video file in the `03_Exports` folder.
*   **Usage:**
    ```bash
    v-flow archive --shoot <YYYY-MM-DD_ShootName> --file <filename.mp4> --tags "Comma, Separated, Tags"
    ```

### `v-flow consolidate`
*   **Purpose:** Finds and copies unique media from an external drive into your archive without creating duplicates.
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