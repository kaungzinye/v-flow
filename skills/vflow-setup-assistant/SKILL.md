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

- Explaining the Archive, Exports, and named Working Location roles.
- Using `v-flow locations` to show current config.
- Using `v-flow set <key> <value>` to update individual paths.
- Using `v-flow make-config` to create a fresh config file when none exists.

Use this skill when:

- v-flow commands fail because config is missing or paths are wrong.
- The user wants to swap a drive (e.g. new archive HDD).
- The user says things like "change my archive drive" or "update my laptop path".

## Config Reference

- **Config file**: `~/.vflow_config.yml`
- `locations.archive` — protected retained storage.
- `locations.exports` — the browsable root for exported videos.
- `locations.working.<name>` — a named location for optional Working Copies, such as `laptop` or `work_ssd`.
- `settings.laptop_free_space_reserve_gb` — free space preserved when the laptop is used for a Working Copy (default 50).
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
v-flow set archive "/Volumes/New Drive/MediaArchive"
```

Valid keys: `archive`, `exports`, `working.<name>`, and `settings.<name>`.

After running, confirm with `v-flow locations`.

### First-time setup (no config file exists)

1. Run `v-flow make-config` to create a sample config.
2. Use `v-flow set` for each role:
   ```bash
   v-flow set archive "/Volumes/Kaung HDD/MediaArchive"
   v-flow set exports "/Volumes/T7/Exports"
   v-flow set working.laptop "/Users/yourname/Working Copies"
   v-flow set working.work_ssd "/Volumes/T7/Working Copies"
   ```
3. Run `v-flow locations` to confirm.

### Inspect config file directly

Read `~/.vflow_config.yml` directly if you need to see the raw YAML. Prefer `v-flow locations` for a cleaner view.

## Clarifying Questions

- "Change my archive drive." → Ask: "What is the new Archive path?" → Run `v-flow set archive "<path>"`.
- "Set this up for me." → Ask for Archive, Exports, and the named Working Locations.
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
