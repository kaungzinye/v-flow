---
name: vflow-ingest-project-assistant
description: Helps users ingest footage from cards or folders and prepare editing projects on their workspace SSD. Use when users say things like "ingest my card", "import to laptop only", or "ingest and set up a project on my SSD".
metadata:
  author: v-flow
  version: 0.1.0
  category: workflow-automation
compatibility: Requires local v-flow CLI, access to configured v-flow locations, and permission to read from cards and write to laptop/workspace folders.
---

# v-flow Ingest & Project Assistant

## Purpose and When to Use

Help the user **ingest footage and photos from a card or folder**, **verify the backup before formatting**, and **prepare an editing project** on their workspace SSD.

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
  - Run local commands like `v-flow ingest`, `v-flow prep`.
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

**`v-flow ingest`** — ingest videos to laptop and archive

- `--source` / `-s` – **required**: folder where video files live (e.g. `/Volumes/CardName/private/M4ROOT/CLIP`).
- `--shoot` / `-n` – shoot name, used when **not** using `--auto`.
- `--auto` / `-a` – infer shoot folder name from file dates.
- `--force` / `-f` – override date-range mismatches when re-using an existing shoot name.
- `--skip-laptop` – skip copying to laptop ingest folder (archive/workspace only).
- `--workspace` / `-w` – also ingest directly to workspace SSD (using configured `work_ssd`).
- `--split-by-gap` – split footage into multiple shoots if there is a time gap of N hours.
- `--files` – optional list of filename patterns/ranges (e.g. `C3317`, `C3317-C3351`) to restrict ingest.

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

**`v-flow prep`** — move shoot from laptop ingest to workspace SSD for editing

- `--shoot` / `-n` – **required**: name of the shoot to move from laptop ingest to workspace SSD.

---

### High-level behavior

Map user phrases to commands:

- “What’s on my card?” / “Show me the card” → `v-flow card-report`.
- “What’s new on the card?” / “What haven’t I ingested?” → `v-flow ingest-report`.
- “Import/ingest videos to laptop” → `v-flow ingest` (laptop + archive, no `--workspace`).
- “Import photos from card” / “Ingest photos” → `v-flow photo-ingest`.
- “Verify the card” / “Can I format?” → `v-flow card-verify`.
- “Ingest and set up a project” / “Move to SSD” → `v-flow ingest` then `v-flow prep`.
- “Ingest directly to SSD as well” → add `--workspace` to `v-flow ingest`.

Always ask short, concrete questions before running commands:

1. **Card/source path** — confirm the mount point (e.g. `/Volumes/Untitled`). For ingest/ingest-report, derive the CLIP folder automatically or ask.
2. **Shoot naming** — for `ingest`: auto vs specific name. For `photo-ingest`: always ask for the shoot name.
3. **Destinations** — for `ingest`: laptop only or also workspace SSD?
4. **Splitting** — if multiple days or gaps, ask about `--split-by-gap`.
5. **File filters** — if clip ranges mentioned, use `--files`.

Show a brief summary before running any command and wait for user confirmation.

After each command, show key results (files copied/skipped/errors, destination paths). Summarize errors clearly with next steps.

---

### Checklist

Before running `ingest`:
- [ ] Exact `--source` path known.
- [ ] `--auto` or `--shoot` chosen.
- [ ] `--workspace` decision made.
- [ ] `--split-by-gap` set or left at default.

Before running `photo-ingest`:
- [ ] Exact `--source` path known (photo folder on card).
- [ ] `--shoot` name confirmed.

Before running `card-verify`:
- [ ] Card root (`--source`) confirmed.
- [ ] `--photo-shoot` name confirmed if card has photos.

Before running `prep`:
- [ ] Shoot name confirmed as it appears in laptop ingest.
- [ ] User understands `prep` moves files (won’t remain in laptop ingest).

### Examples

- "What's on my card?" → `v-flow card-report --source /Volumes/Untitled`
- "Ingest my card." → ask for card path, shoot naming, destination; run `v-flow ingest-report` first, then `v-flow ingest`.
- "Import the photos from Rome." → `v-flow photo-ingest --source /Volumes/Untitled/DCIM/100MSDCF --shoot "2026-05-06_to_2026-05-13 Rome"`
- "Can I format the card?" → `v-flow card-verify --source /Volumes/Untitled --photo-shoot "2026-05-06_to_2026-05-13 Rome"`
- "Prep the Stockholm shoot." → `v-flow prep --shoot "Stockholm"` after confirming name in laptop ingest.
- "Import to laptop, don't touch SSD." → `v-flow ingest` without `--workspace`; no `prep` unless asked.

## Troubleshooting

- **Ingest fails due to config**: Use the setup assistant to fix `~/.vflow_config.yml`, then retry `v-flow ingest`.
- **Card path wrong**: Ask the user to confirm the mounted card path and re-run with the corrected `--source`.
- **Not enough disk space**: Summarize required vs available space (from CLI output) and suggest ingesting to the drive with more space or freeing space first.
- **card-verify FAIL**: Do not format. Check which files are missing, ingest/photo-ingest them, then re-run card-verify.
- **photo-ingest skipping unexpectedly**: Confirms files are already in that shoot folder — not a false positive from another shoot.

