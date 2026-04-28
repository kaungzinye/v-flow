---
name: vflow-setup-assistant
description: Guides users through configuring v-flow locations and settings. Use when users say "set up v-flow", "fix my v-flow config", "change where footage is stored", "swap my archive drive", or "validate my v-flow setup".
metadata:
  author: v-flow
  version: 0.2.0
  category: configuration
compatibility: Requires local v-flow CLI, shell access, and permission to read and write ~/.vflow_config.yml.
---

# v-flow Setup Assistant

## Purpose and When to Use

Help a videographer configure v-flow **without hand-editing YAML**, by:

- Explaining what each logical location means (`laptop`, `work_ssd`, `archive_hdd`).
- Using `v-flow locations` to show current config.
- Using `v-flow set <key> <value>` to update individual paths.
- Using `v-flow make-config` to create a fresh config file when none exists.

Use this skill when:

- v-flow commands fail because config is missing or paths are wrong.
- The user wants to swap a drive (e.g. new archive HDD).
- The user says things like "change my archive drive" or "update my laptop path".

## Config Reference

- **Config file**: `~/.vflow_config.yml`
- `locations.laptop` — where newly-ingested media lands on the laptop.
- `locations.work_ssd` — fast SSD for active editing projects.
- `locations.archive_hdd` — large drive for long-term storage (root path, e.g. `/Volumes/Kaung HDD/MediaArchive`).
- `settings.default_split_gap` — hours between clips used to auto-split shoots (default 24).

## CLI Commands

| Command | Purpose |
|---|---|
| `v-flow locations` | Show all configured paths + whether each is currently mounted |
| `v-flow set <key> <value>` | Update one path or setting without re-running full setup |
| `v-flow make-config` | Create a blank sample config at `~/.vflow_config.yml` |

**There is no `v-flow setup` or `v-flow config-validate` command.** Do not attempt to run these.

## Core Workflows

### Check current config

```bash
v-flow locations
```

Shows all configured paths and a `✓`/`✗ not mounted` indicator for each. Use this first to understand what's configured before making changes.

### Update a single location (most common — e.g. swapping HDD)

```bash
v-flow set archive_hdd "/Volumes/New Drive/MediaArchive"
```

Valid keys: `laptop`, `work_ssd`, `archive_hdd`, `settings.default_split_gap`.

After running, confirm with `v-flow locations`.

### First-time setup (no config file exists)

1. Run `v-flow make-config` to create a sample config.
2. Use `v-flow set` for each location:
   ```bash
   v-flow set laptop "/Users/yourname/Desktop/Ingest"
   v-flow set work_ssd "/Volumes/T7/Videos/Project Files"
   v-flow set archive_hdd "/Volumes/Kaung HDD/MediaArchive"
   ```
3. Run `v-flow locations` to confirm.

### Inspect config file directly

Read `~/.vflow_config.yml` directly if you need to see the raw YAML. Prefer `v-flow locations` for a cleaner view.

## Clarifying Questions

- "Change my archive drive." → Ask: "What is the new archive drive path?" → Run `v-flow set archive_hdd "<path>"`.
- "Set this up for me." → Ask for each of: laptop path, work SSD path, archive HDD path → Run three `v-flow set` commands.
- "v-flow says config is invalid / missing." → Run `v-flow make-config` then the `v-flow set` commands above.

## Safety Rules

Before calling setup complete:

- [ ] `v-flow locations` runs without errors.
- [ ] Each configured path shows `✓` (or the user understands which ones aren't currently mounted and why).
- [ ] The user knows which folder is laptop ingest, which is workspace SSD, and which is archive.

## Troubleshooting

- **Config missing**: Run `v-flow make-config`, then `v-flow set` for each location.
- **Path wrong**: Run `v-flow set <key> "<correct path>"` and confirm with `v-flow locations`.
- **Drive not mounted** (shows `✗`): Expected when that drive isn't plugged in. Config is still valid — the path will resolve when the drive is connected.
