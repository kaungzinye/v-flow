---
name: vflow-ingest-project-assistant
description: Helps users preserve footage as Archive Import Batches and explicitly check out Working Copies for editing. Use when users say things like "ingest my card", "work on this Shoot from my SSD", or "edit directly from the Archive".
metadata:
  author: v-flow
  version: 0.1.0
  category: workflow-automation
compatibility: Requires local v-flow CLI, access to configured v-flow locations, and permission to read cards and write the Archive or a chosen Working Location.
---

# v-flow Ingest & Project Assistant

## Purpose and When to Use

Help the user **ingest footage and photos from a card or folder**, **verify archived media before formatting**, and **create an optional Working Copy** at an explicitly selected location.

This skill translates natural-language requests like:

- “What’s on my card?”
- “Ingest yesterday’s card.”
- “Import photos from the card.”
- “Verify before I format.”
- “Set up a project on my SSD.”

into concrete v-flow commands.

## Clarifying Questions and Defaults

Assumptions:

- v-flow is installed and configured (use the **v-flow Setup Assistant** skill first if not).
- The agent can:
  - Run local commands like `v-flow ingest` and `v-flow checkout`.
  - Ask the user simple questions and wait for answers.

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

### Full card-offload workflow (recommended order)

1. **See what’s on the card** — `v-flow card-report --source <card-root>`
2. **Check which videos are new** — `v-flow ingest-report --source <card-clip-folder>`
3. **Ingest new videos** — `v-flow ingest --source <card-clip-folder> ...`
4. **Import new photos** — `v-flow photo-ingest --source <card-photo-folder> --shoot “<name>”`
5. **Verify before formatting** — `v-flow card-verify --source <card-root> --photo-shoot “<name>”`

Only after card-verify PASSES is it safe to format the card.

---

### Commands and their options

**`v-flow card-report`** — see what’s on the card before doing anything

- `--source` / `-s` – **required**: card root (e.g. `/Volumes/Untitled`).
- Auto-detects `private/M4ROOT/CLIP` for videos and `DCIM/100MSDCF` for photos.
- Groups by date, shows first/last filename, count, and whether videos are already in archive.

**`v-flow ingest-report`** — check which videos are new (not yet in laptop or archive)

- `--source` / `-s` – **required**: card CLIP folder (e.g. `/Volumes/Untitled/private/M4ROOT/CLIP`).
- `--priority-day` – highlight a specific day of month (default 28).
- Compares against both laptop ingest and archive by name+size.

**`v-flow ingest`** — preserve an immutable Archive Import Batch

- `--source` / `-s` – **required**: folder where video files live (e.g. `/Volumes/CardName/private/M4ROOT/CLIP`).
- `--shoot` / `-n` – shoot name, used when **not** using `--auto`.
- `--auto` / `-a` – infer shoot folder name from file dates.
- `--import-batch` – optional stable Import Batch identity; v-flow derives one from content when omitted.
- `--files` – optional list of filename patterns/ranges (e.g. `C3317`, `C3317-C3351`) to restrict ingest.
- Preserves the received hierarchy in the Archive, verifies checksums, and creates no Working Copy.

**`v-flow checkout`** — create an optional Working Copy or use Direct Archive Access

- `--shoot` / `-n` – **required**: archived Shoot identity.
- `--working-location` / `-l` – an explicit configured Working Location name such as `work_ssd` or `laptop`.
- `--direct-archive-access` – report the archived source path and create no Working Copy.
- `--dry-run` – verify and preview the plan without copying.
- Choose exactly one of `--working-location` and `--direct-archive-access`.
- Laptop Checkout enforces `settings.laptop_free_space_reserve_gb`; never choose another device after a capacity failure.

**`v-flow photo-ingest`** — copy RAW photos to Photo/RAW archive

- `--source` / `-s` – **required**: folder with RAW files (e.g. `/Volumes/Untitled/DCIM/100MSDCF`).
- `--shoot` / `-n` – **required**: shoot name in Photo/RAW (e.g. `”2026-05-06_to_2026-05-13 Rome”`).
- Skips files already in that specific shoot folder (not archive-wide — avoids Sony filename-recycling false positives).
- Preserves timestamps. Supports: ARW, CR2, CR3, NEF, DNG, ORF, RW2.

**`v-flow card-verify`** — verify card is fully backed up before formatting

- `--source` / `-s` – **required**: card root (e.g. `/Volumes/Untitled`).
- `--photo-shoot` – name of the photo shoot to verify against (required if card has photos).
- Videos checked archive-wide (Video/RAW) by name+size.
- Photos checked against specific shoot folder only (Photo/RAW/<photo-shoot>).
- Reports PASS/FAIL separately for videos and photos with overall verdict.

### High-level behavior

Map user phrases to commands:

- “What’s on my card?” / “Show me the card” → `v-flow card-report`.
- “What’s new on the card?” / “What haven’t I ingested?” → `v-flow ingest-report`.
- “Import/ingest videos” → `v-flow ingest` to preserve them in the Archive.
- “Import photos from card” / “Ingest photos” → `v-flow photo-ingest`.
- “Verify the card” / “Can I format?” → `v-flow card-verify`.
- “Ingest and set up for editing” → `v-flow ingest`, then `v-flow checkout --working-location <explicit-name>`.
- “Move to SSD” / “Work on this Shoot from SSD” → `v-flow checkout --working-location work_ssd` after confirming the configured name.
- “Use the Archive directly” → `v-flow checkout --direct-archive-access`.

Always ask short, concrete questions before running commands:

1. **Card/source path** — confirm the mount point (e.g. `/Volumes/Untitled`). For ingest/ingest-report, derive the CLIP folder automatically or ask.
2. **Shoot naming** — for `ingest`: auto vs specific name. For `photo-ingest`: always ask for the shoot name.
3. **Editing mode** — after ingest, ask whether the user wants a named Working Location or Direct Archive Access.
4. **File filters** — if clip ranges are mentioned, use `--files`.

Show a brief summary before running any command and wait for user confirmation.

After each command, show key results (files copied/skipped/errors, destination paths). Summarize errors clearly with next steps.

---

### Checklist

Before running `ingest`:
- [ ] Exact `--source` path known.
- [ ] `--auto` or `--shoot` chosen.
- [ ] Import Batch identity is supplied or intentionally derived.

Before running `photo-ingest`:
- [ ] Exact `--source` path known (photo folder on card).
- [ ] `--shoot` name confirmed.

Before running `card-verify`:
- [ ] Card root (`--source`) confirmed.
- [ ] `--photo-shoot` name confirmed if card has photos.

Before running `checkout`:
- [ ] Shoot identity is confirmed.
- [ ] Exactly one explicit mode is chosen: a named Working Location or Direct Archive Access.
- [ ] `--dry-run` is run before a Working Copy when the user wants a capacity preview.

### Examples

- "What's on my card?" → `v-flow card-report --source /Volumes/Untitled`
- "Ingest my card." → ask for card path, shoot naming, destination; run `v-flow ingest-report` first, then `v-flow ingest`.
- "Import the photos from Rome." → `v-flow photo-ingest --source /Volumes/Untitled/DCIM/100MSDCF --shoot "2026-05-06_to_2026-05-13 Rome"`
- "Can I format the card?" → `v-flow card-verify --source /Volumes/Untitled --photo-shoot "2026-05-06_to_2026-05-13 Rome"`
- "Check out the Stockholm Shoot to my SSD." → `v-flow checkout --shoot "Stockholm" --working-location work_ssd` after confirming the configured name.
- "Edit Stockholm directly from the Archive." → `v-flow checkout --shoot "Stockholm" --direct-archive-access`.

## Troubleshooting

- **Ingest fails due to config**: Use the setup assistant to fix `~/.vflow_config.yml`, then retry `v-flow ingest`.
- **Card path wrong**: Ask the user to confirm the mounted card path and re-run with the corrected `--source`.
- **Laptop Checkout lacks space**: Summarize required, free, and reserved space. Ask the user to free space, explicitly choose another named location, or use Direct Archive Access. Never fall back automatically.
- **Working Copy conflict**: Stop. Existing content differs from the archived checksum and Checkout leaves it untouched.
- **card-verify FAIL**: Do not format. Check which files are missing, ingest/photo-ingest them, then re-run card-verify.
- **photo-ingest skipping unexpectedly**: Confirms files are already in that shoot folder — not a false positive from another shoot.
