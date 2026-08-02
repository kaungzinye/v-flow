# v-flow

v-flow helps videographers move footage between a camera card, long-term storage, and an editing drive without losing track of the safe copy.

It can:

- copy a card or footage folder to a long-term drive and verify every file;
- make a temporary copy on a laptop or SSD for editing;
- save finished videos and DaVinci Resolve project backups;
- remove temporary editing copies only after safety checks pass.

You can use the `v-flow` terminal command directly, or ask Codex, Claude Code, or Cursor in plain language.

## The four places v-flow uses

You only need to choose where these live:

| Place | Plain meaning |
|---|---|
| Archive | Your protected, long-term media storage, usually an HDD. v-flow copies files here and verifies them. |
| Exports | The folder where completed videos and graded clips appear before they are archived. |
| Working location | A laptop or fast SSD where you may keep temporary footage for editing. You can configure more than one. |
| Camera card or source folder | The footage you are bringing into v-flow. v-flow leaves it unchanged. |

The sections below follow one typical workflow from camera card to finished project.

## Install

Run:

```bash
curl -fsSL https://raw.githubusercontent.com/kaungzinye/v-flow/main/install_vflow.sh | bash
```

This installs the `v-flow` command and one `vflow` skill for Codex, Claude Code, and Cursor.

From a local checkout, refresh only the skill:

```bash
./install_vflow.sh --skills-only
```

## Set up your drives

The easiest setup is to ask in plain language:

> Set up v-flow. My long-term archive is on this HDD, my exports are here, and I edit from this SSD.

The skill explains each location, confirms the exact paths, and configures them one at a time.

To configure from the terminal instead:

```bash
v-flow make-config
v-flow set archive "/Volumes/Archive/Media"
v-flow set exports "/Volumes/Work/Exports"
v-flow set working.work_ssd "/Volumes/Work/Working Copies"
v-flow set working.laptop "/Users/you/Working Copies"
v-flow set settings.laptop_free_space_reserve_gb 50
v-flow locations
```

A **working location** is simply a named laptop or drive where v-flow may place temporary editing media. Names such as `work_ssd` and `laptop` are your choices.

## Your first footage workflow

### 1. Copy footage from a card

You can say:

> Ingest this card using v-flow.

In v-flow, **ingest** means preserving one card or source folder in the Archive while leaving the source unchanged.

```bash
v-flow ingest --source "/Volumes/SDCARD" --shoot "2026-08-02_Stockholm"
```

The name `2026-08-02_Stockholm` identifies the **Shoot**: footage captured in a certain date range and stored as one named collection.

Each individual card or folder copied into that Shoot becomes an **Import Batch**. v-flow keeps the received folder structure and companion files together, then writes a checksum manifest that proves what reached the Archive.

After a successful ingest:

- the Archive contains one verified copy;
- the card or source folder remains unchanged;
- no footage has been copied to your editing SSD yet.

Use `--auto` instead of `--shoot` when you want v-flow to derive the Shoot name from media dates.

### 2. Put archived footage on an editing drive

You can say:

> Put the Stockholm footage on my SSD so I can edit it.

**Checkout** creates a verified **Working Copy**—a temporary copy of archived footage on the laptop or SSD you choose.

Preview first, then copy:

```bash
v-flow checkout --shoot "2026-08-02_Stockholm" --working-location work_ssd --dry-run
v-flow checkout --shoot "2026-08-02_Stockholm" --working-location work_ssd
```

If the Archive is fast enough to edit from directly, use:

```bash
v-flow checkout --shoot "2026-08-02_Stockholm" --direct-archive-access
```

This **Direct Archive Access** mode reports the archived footage paths and creates no Working Copy.

### 3. Save finished videos

Place completed renders under the configured Exports folder.

A complete edited video is a **Final Video**:

```bash
v-flow archive --type final-video --project "Summer Film" --file "final.mov" --dry-run
v-flow archive --type final-video --project "Summer Film" --file "final.mov"
```

A reusable source clip with its Resolve grade baked in is a **Graded Select**:

```bash
v-flow archive --type graded-select --shoot "2026-08-02_Stockholm" --file "select.mov" --dry-run
v-flow archive --type graded-select --shoot "2026-08-02_Stockholm" --file "select.mov"
```

Archiving an export copies and verifies it in long-term storage. The local export remains in place.

### 4. Save the Resolve project

You can say:

> Finish the Summer Film project.

In v-flow, **Finish** means all required final videos are safely archived and DaVinci Resolve has exported a verified portable **Project Backup** containing the edit, grades, stills, and LUTs.

```bash
v-flow finish --project "Summer Film" --dry-run
v-flow finish --project "Summer Film"
```

Finish keeps local files. It does not free drive space.

### 5. Free space on the editing drive

You can say:

> Remove the temporary Stockholm footage from my SSD.

**Cleanup** removes only a Working Copy. Before deletion, it verifies the Archive copy, checks the Resolve project by default, previews the exact files, and asks for confirmation.

```bash
v-flow cleanup --shoot "2026-08-02_Stockholm" --working-location work_ssd --project "Summer Film" --dry-run
v-flow cleanup --shoot "2026-08-02_Stockholm" --working-location work_ssd --project "Summer Film"
```

Cleanup never targets the Archive.

## Ask in ordinary language

For example:

- “Back up my footage folder to this HDD using v-flow.”
- “Copy this camera card somewhere safe.”
- “Put the Stockholm footage on my SSD for editing.”
- “Save this final export.”
- “Back up my Resolve project.”
- “Remove the temporary editing copy after checking it is safe.”
- “Restore this archived folder to my Desktop.”
- “Show me duplicate clips from the last day.”

## Which operation do I want?

| What you want | v-flow operation |
|---|---|
| Preserve a camera card or received source folder | Ingest |
| Make archived footage available on a laptop or SSD | Checkout |
| Edit directly from the Archive | Direct Archive Access |
| Retain a completed video or graded clip | Archive |
| Retain a portable Resolve project backup | Finish |
| Remove a verified temporary editing copy | Cleanup |
| Copy an arbitrary existing folder to the Archive | Backup |
| Copy something out of the Archive | Restore |
| Inspect possible duplicates without deleting them | List duplicates |

If the source is a camera card, use Ingest because it preserves the received hierarchy and records an Import Batch. Use Backup for an ordinary folder that is not a new card ingest.

## Other useful commands

Inspect a card or check what still needs ingesting:

```bash
v-flow card-report --source "/Volumes/SDCARD"
v-flow ingest-report --source "/Volumes/SDCARD/private/M4ROOT/CLIP"
v-flow card-verify --source "/Volumes/SDCARD" --photo-shoot "Iceland"
```

Back up and verify an arbitrary folder:

```bash
v-flow backup --source "/Users/you/Desktop/Footage" --destination "Video/Backups/Footage" --dry-run
v-flow backup --source "/Users/you/Desktop/Footage" --destination "Video/Backups/Footage"
v-flow verify-backup --source "/Users/you/Desktop/Footage" --destination "/Volumes/Archive/Media/Video/Backups/Footage"
```

Restore archived files:

```bash
v-flow restore --source "Camera Originals/2026-08-02_Stockholm" --destination "/Users/you/Desktop/Recovered" --dry-run
```

Inspect duplicate candidates without deleting anything:

```bash
v-flow list-duplicates --location both --past-hours 24
```

Use `v-flow --help` for the complete command list and `v-flow <command> --help` for current options.

## Development

Install the package from the checkout and run the tests:

```bash
python3 -m pip install -e .
pytest
```
