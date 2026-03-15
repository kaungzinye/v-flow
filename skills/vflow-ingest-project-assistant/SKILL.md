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

Help the user **ingest footage** from a card or folder and **prepare an editing project** on their workspace SSD.

This skill translates natural-language requests like:

- “Ingest yesterday’s card.”
- “Import to laptop only.”
- “Ingest and set up a project on my SSD.”

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

Core commands:

- `v-flow ingest` → calls `ingest_service.ingest_shoot` under the hood.
- `v-flow prep` → calls `ingest_service.prep_shoot`.

Key options and their meanings:

For ingest:

- `--source` / `-s` – **required**: folder where video files live.
  - Typical SD card folder: `"/Volumes/CardName/private/M4ROOT/CLIP"` (Sony, etc.).
- `--shoot` / `-n` – shoot name, used when **not** using `--auto`.
- `--auto` / `-a` – infer shoot folder name from file dates.
- `--force` / `-f` – override date-range mismatches when re-using an existing shoot name.
- `--skip-laptop` – skip copying to laptop ingest folder (archive/workspace only).
- `--workspace` / `-w` – also ingest directly to workspace SSD (using configured `work_ssd`).
- `--split-by-gap` – split footage into multiple shoots if there is a time gap of N hours.
- `--files` – optional list of filename patterns/ranges (e.g. `C3317`, `C3317-C3351`) to restrict ingest.

For prep:

- `--shoot` / `-n` – name of the shoot to move from laptop ingest to workspace SSD.

High-level behavior:

1. Interpret intent

Map user phrases to ingest/prep behavior:

- “Import/ingest to laptop” → `v-flow ingest` with:
  - `--source` as provided or clarified.
  - No `--workspace` flag (laptop + archive only).
- “Ingest and set up a project”, “prep for editing”, “move to SSD” →
  - Run `v-flow ingest` first (if footage is still on card).
  - Then run `v-flow prep --shoot <name>` to move files from laptop ingest to `work_ssd`.
- “Ingest directly to SSD as well” →
  - Add `--workspace` to the ingest command.

Always ask short, concrete questions before running ingest:

1. **Source path**
   - Example: “Where are the camera files? (e.g. `/Volumes/Card/private/M4ROOT/CLIP`)"
   - If user says just “from the card”, ask them to confirm the mount path.

2. **Shoot naming**
   - If the user doesn’t specify:
     - Ask: “Do you want me to **auto-name** the shoot based on dates, or use a specific name?”
   - If they choose auto:
     - Use `--auto` and omit `--shoot`.
   - If they provide a name:
     - Use `--shoot "<name>"` (no `--auto`).

3. **Destinations: laptop vs workspace SSD**
   - Ask: “Should I ingest to laptop only, or also ingest directly to your workspace SSD?”
   - Map answers:
     - “Laptop only” → no `--workspace`.
     - “Also SSD” → add `--workspace`.

4. **Splitting by time gap**
   - If they mention multiple days or long gaps, or say “split into parts”:
     - Ask: “Do you want me to auto-split this into separate shoots when there’s a gap of more than N hours? If so, how many hours?”
     - Use `--split-by-gap N`. If they’re unsure, you can suggest using the default from config.

5. **File filters (optional)**
   - If they mention specific clip ranges:
     - Example: “Only C3317 to C3351.”
     - Use `--files "C3317-C3351"`.

When you have all needed information:

- Construct the `v-flow ingest` command explicitly.
- Echo a brief summary to the user before running, for example:

> “I’ll ingest from `/Volumes/Card/private/M4ROOT/CLIP` to your laptop ingest and archive, auto-naming the shoot based on dates, and also ingest directly to your workspace SSD. OK?”

Only run the command after the user confirms.

If the user also asked to “set up a project”, then:

- After successful ingest, run:
  - `v-flow prep --shoot "<shoot-name>"`
  - Here `<shoot-name>` is either:
    - The name they provided with `--shoot`, or
    - The auto-named shoot that ingest reported (if ingest output includes it), or
    - A name you ask them to confirm if ambiguous.

After each command:

- Show key high-level results, not every log line:
  - Number of files ingested, skipped, or errored.
  - Final shoot folder path(s) on laptop and/or workspace SSD.
- If there were errors (e.g. disk full), summarize them clearly and suggest next steps.

Examples:

- “Ingest my card.”
  - Ask:
    - “Which folder on the card has the video clips? (For Sony, this is usually the `CLIP` folder.)”
    - “Do you want me to auto-name the shoot, or use a specific shoot name?”
    - “Ingest to laptop only, or also to your workspace SSD?”

- “Prep the Stockholm shoot.”
  - Run `v-flow prep --shoot "Stockholm"` after confirming the exact name as it appears in the ingest folder.

- “Import to laptop, don’t touch SSD.”
  - Use `v-flow ingest` **without** `--workspace`.
  - Do not run `prep` unless they explicitly ask for project setup.

Before running ingest:

- [ ] You know the exact `--source` path.
- [ ] You know whether you’re using `--auto` or `--shoot`.
- [ ] You know whether to include `--workspace`.
- [ ] You’ve confirmed or reasonably set `--split-by-gap` (or left it at config default / zero).

Before running prep:

- [ ] The shoot name is confirmed with the user.
- [ ] You understand that prep moves files from laptop ingest to workspace SSD (i.e. they won’t remain in laptop ingest).

## Troubleshooting

- **Ingest fails due to config**: Use the setup assistant to fix `~/.vflow_config.yml`, then retry `v-flow ingest`.
- **Card path wrong**: Ask the user to confirm the mounted card path and re-run ingest with the corrected `--source`.
- **Not enough disk space**: Summarize required vs available space (from CLI output) and suggest ingesting to the drive with more space or freeing space first.

