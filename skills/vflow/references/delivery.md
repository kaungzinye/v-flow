# Save finished videos and the Resolve project

First identify what the user wants to retain:

- **Final Video** — a completed edited timeline export.
- **Graded Select** — a chosen source clip exported with its Resolve grade baked in for viewing or reuse.
- **Project Backup** — a portable Resolve snapshot containing the edit and grades without duplicating the original footage.

## Save a finished video or graded clip

**Archive** copies and verifies one of these exports in long-term storage.

1. Ask whether the file is a complete edited video or a reusable graded clip.
   - For a Final Video, resolve the Project and file beneath `Exports/Final Videos/<Project>`.
   - For a Graded Select, resolve the Shoot and file beneath `Exports/Graded Selects/<Shoot>`.

   Complete when the file type, owner name, and relative filename are exact.

2. Run the matching preview:

   ```bash
   v-flow archive --type final-video --project <project> --file <file> --dry-run
   v-flow archive --type graded-select --shoot <shoot> --file <file> --dry-run
   ```

   Summarize the source and destination. Continue without `--dry-run` after approval.

   Complete when the Archive checksum verifies and the local export remains present.

3. Report the local path, Archive path, copied or already-verified result, and checksum.

## Save the Resolve project

**Finish** completes a Project when its required Final Videos and a portable Project Backup are verified in long-term storage. Finish keeps local files.

1. Resolve the Project in the user's language and confirm which final outputs belong to it.
2. Run `v-flow finish --project <project> --dry-run`.
3. Explain the planned Resolve backup and any missing retained output. After approval, run `v-flow finish --project <project>`.
4. Report retained videos, the Project Backup path, copied or already-present files, and local retention.

Complete when Resolve exports a verified Project Backup with stills and LUTs and every local file remains present.

## Copy metadata

When the user wants metadata copied into exports, resolve the exact original and export folders, explain that target-file metadata changes in place, then run:

```bash
v-flow copy-meta --source-folder <source> --target-folder <target>
```

Complete when updated and unmatched targets are reported.

## Safety gates

- Associate a Final Video with a Project and a Graded Select with a Shoot.
- Keep Archive and Finish copy-only.
- Access Resolve through the supported adapter.
