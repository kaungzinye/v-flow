# Back up or restore an ordinary folder

Use this branch for an existing folder that is not a newly received camera card. A camera card belongs in Ingest because Ingest preserves the received hierarchy and records it as an Import Batch.

In this branch, **Backup** copies an ordinary folder into the configured long-term Archive and keeps the source. **Restore** copies something out of the Archive and also keeps the archived source.

## Back up a folder

1. Resolve the exact source folder and where it should live under the Archive. If the user says “HDD,” confirm whether that drive is the configured Archive. Route drive configuration to Setup when needed.

2. Preview:

   ```bash
   v-flow backup --source <source> --destination <archive-relative-path> --dry-run
   ```

   Complete when the files that would copy, files already present, and errors are visible.

3. Explain that the source remains in place. After approval, run the same command without `--dry-run`.

4. When the user asks for proof, or a later step depends on it, run:

   ```bash
   v-flow verify-backup --source <source> --destination <destination>
   ```

   Use `--archive-wide` only when the user intentionally wants filename-and-size matching anywhere beneath the destination instead of the same relative paths.

Complete when the intended files exist at the destination and the source remains present.

## Inspect existing backups

Run `v-flow list-backups --subpath <archive-relative-path>`.

Complete when each backup is reported with its path, file count, size, and modification time.

## Copy files out of the Archive

Use `v-flow restore` for a specific archived file or directory:

```bash
v-flow restore --source <archive-source> --destination <destination> --dry-run
```

Use `v-flow restore-folder` for a general backup folder tree:

```bash
v-flow restore-folder --source <source> --destination <destination> --dry-run
```

Explain the planned destination and conflicts. Continue after approval only with a conflict-free plan.

Complete when the destination verifies and the archived source remains unchanged.

## Safety gates

- Keep Backup and Restore copy-only.
- Stop on a path escape, content conflict, or failed verification.
- Use Cleanup when the user wants to remove a temporary Checkout-created editing copy.
