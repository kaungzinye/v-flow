---
name: vflow-setup-assistant
description: Guides users through configuring v-flow locations and settings. Use when users say "set up v-flow", "fix my v-flow config", "change where footage is stored", or "validate my v-flow setup".
metadata:
  author: v-flow
  version: 0.1.0
  category: configuration
compatibility: Requires local v-flow CLI, shell access, and permission to read and write ~/.vflow_config.yml.
---

# v-flow Setup Assistant

## Purpose and When to Use

Help a videographer (or any user) get v-flow configured on their machine **without hand-editing YAML**, by:

- Explaining what each logical location means (`laptop`, `work_ssd`, `archive_hdd`).
- Driving the interactive config wizard (`v-flow setup`) when possible.
- Safely inspecting and, if needed, editing `~/.vflow_config.yml`.
- Validating that the resulting config is usable.

This skill is **tool-agnostic**. It assumes the agent can:

- Run local shell commands (e.g. `v-flow setup`, `v-flow config-validate`).
- Read and write local files (especially `~/.vflow_config.yml`).

- v-flow reads a single YAML config file at: `~/.vflow_config.yml`.
- The config has two main sections:
  - `locations` – named folders on the user’s system.
    - `laptop`: where newly-ingested media lands first on their laptop.
    - `work_ssd`: a fast SSD or workspace drive for active projects.
    - `archive_hdd`: a large HDD (or RAID) used for long-term storage.
  - `settings` – optional knobs and defaults, such as:
    - `default_split_gap` (hours between clips used to auto-split shoots).
    - `default_backup_source` (a default folder to back up when the user says “back up my stuff”).

Your job is **not** to guess random paths. Your job is to:

- Ask the user where these live on *their* system.
- Use the v-flow CLI’s setup helpers to write a valid config.
- Show them exactly what changed.

Use this skill when:

- v-flow commands like `v-flow ingest` fail because the config is missing or broken.
- The user says things like:
  - “Set up v-flow on this machine.”
  - “I just installed v-flow, what do I do first?”
  - “Change my archive drive, I bought a new one.”
  - “v-flow says my config is invalid.”

## Core Workflows

- **Config file**: `~/.vflow_config.yml`
- **Primary wizard**: `v-flow setup`
- **Sample generator**: `v-flow make-config`
- **Validation**: `v-flow config-validate`

1. **Check if config exists**
   - Run: `v-flow config-validate`
   - Behaviors:
     - If it succeeds: explain that v-flow is already configured and show the configured locations. Ask if they want to change anything.
     - If it fails due to missing file or invalid structure: proceed to the setup wizard.

2. **Explain what will happen**
   - In simple language, tell the user:
     - You will run `v-flow setup`.
     - It will create or update `~/.vflow_config.yml`.
     - It does **not** move or delete any media; it only records the paths.

3. **Run the setup wizard**
   - Command: `v-flow setup`
   - The wizard will ask about:
     - Laptop ingest folder (`laptop`).
     - Workspace SSD/projects folder (`work_ssd`).
     - Archive drive root (`archive_hdd`).
     - Optional settings like `default_split_gap` and `default_backup_source`.
   - Your behavior:
     - Help the user pick paths by:
       - Suggesting sensible defaults (e.g. `~/Desktop/Ingest` for laptop ingest).
       - Mentioning detected volumes (e.g. under `/Volumes` on macOS) when appropriate.
     - Keep answers short and concrete. Avoid jargon like “YAML schema”.

4. **Validate after wizard completes**
   - Immediately run: `v-flow config-validate`
   - Summarize:
     - Which logical locations are configured.
     - Which ones point to existing folders vs. missing ones.
   - If some folders don’t exist yet:
     - Explain that it’s okay; they can create those folders later.
     - Offer to:
       - Show them the config file.
       - Re-run `v-flow setup` after they create the folders.

Sometimes you may need to inspect or edit `~/.vflow_config.yml` directly (for example, to fix a typo in a path).

When you do this, follow these rules:

1. **Always read first, never overwrite blindly**
   - Read the existing YAML.
   - Preserve all keys you don’t explicitly intend to change.

2. **Show a before/after summary**
   - For each changed location, show:
     - Old path → new path (one line).
   - Confirm with the user before writing changes.

3. **Write once, validate once**
   - After writing:
     - Run `v-flow config-validate`.
     - Report any issues and propose concrete fixes.

4. **Never delete the config file without explicit consent**
   - If the file is badly corrupted, propose:
     - Backing it up (e.g. `~/.vflow_config.yml.bak`).
     - Creating a fresh config using `v-flow setup` or `v-flow make-config`.

## Clarifying Questions and Defaults

Examples of ambiguous user requests and how to respond:

- “Set this up for me.”
  - Ask:
    - “Where do you usually copy camera cards to on your laptop?”
    - “Where is your fast SSD for editing projects?”
    - “Where is your big archive drive?”
  - Then run the wizard.

- “Change my archive drive.”
  - Use `v-flow config-validate` or read `~/.vflow_config.yml` to see current `archive_hdd`.
  - Ask:
    - “What is the new archive drive path you want v-flow to use?”
  - Update only the `archive_hdd` location, then validate.

- “v-flow says config is invalid.”
  - Run `v-flow config-validate` and surface the exact errors.
  - Decide whether to:
    - Fix paths directly, or
    - Re-run `v-flow setup` for a clean reset.

## Safety Rules

Before saying “setup complete”, ensure:

- [ ] `~/.vflow_config.yml` exists.
- [ ] `v-flow config-validate` runs without errors (or any warnings are clearly explained).
- [ ] The user understands which folders are:
  - Laptop ingest (where new footage will go).
  - Workspace SSD (where projects will live).
  - Archive drive (where backups and archives live).

## Troubleshooting

- **Config file missing**: Run `v-flow setup` to create a fresh config, then `v-flow config-validate` to confirm it works.
- **Config invalid YAML**: Back up `~/.vflow_config.yml` to `~/.vflow_config.yml.bak`, fix only the broken section (usually indentation or a missing colon), then validate again.
- **Paths no longer valid**: Ask the user about new locations, update only those keys in YAML, and run `v-flow config-validate`.

## References

- v-flow CLI entrypoint: `v-flow`
- Main config file: `~/.vflow_config.yml`
- Related commands: `v-flow setup`, `v-flow config-validate`, `v-flow make-config`

