# Set up drives

Explain the storage choices before asking for paths:

- **Archive** — the protected, long-term location for original footage and retained outputs; usually an HDD.
- **Exports** — the folder where rendered videos appear before v-flow copies them into long-term storage.
- **Working location** — a named laptop or fast drive that may hold temporary footage for editing.

## Configure

1. Run `v-flow locations` to inspect what is already configured.

   Complete when each existing location has a path and availability result, or configuration is absent.

2. If configuration is absent, run `v-flow make-config`. Ask for one location at a time, explain its purpose, and set the confirmed path:

   ```bash
   v-flow set archive <path>
   v-flow set exports <path>
   v-flow set working.<name> <path>
   v-flow set settings.laptop_free_space_reserve_gb <number>
   ```

   Complete when the long-term Archive, Exports folder, at least one editing location, and laptop free-space reserve are explicit.

3. Run `v-flow locations` again.

   Complete when the CLI accepts the configuration and unavailable drives are clearly identified without changing their saved paths.

## Refresh the installed skill

When the user wants installed v-flow guidance refreshed from a trusted checkout:

1. Show the repository and target skill directories.
2. Run `./install_vflow.sh --skills-only` from the checkout.
3. Confirm each target contains the checkout's single `vflow` skill.

Complete when Codex, Claude Code, and Cursor copies match the checkout. Media and configuration remain unchanged.

## Safety gates

- Change one confirmed setting at a time.
- Keep setup operations outside media folders.
- Treat an unplugged drive as unavailable, not as permission to choose another path.
