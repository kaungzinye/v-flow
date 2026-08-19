---
name: vflow
description: v-flow stores and moves video footage and photos safely. Use whenever v-flow comes up, or when the user wants to set up media drives, copy a camera card, archive or restore media, free editing space, or find duplicates.
---

# v-flow

v-flow keeps protected long-term storage separate from temporary editing copies. It manages video footage in Shoots and photos in Collections. For any other media, state that v-flow does not manage it and leave the files where they are.

These terms control choices across branches:

- **Archive** — protected long-term media storage, usually an HDD. v-flow copies and verifies files here.
- **Working Copy** — a temporary copy of archived footage on a laptop or SSD for editing.
- **Shoot** — footage captured in a certain date range and stored as one named flat folder.
- **Collection** — the photos from one Shoot's card, stored as one named flat folder. One ingest names the Collection after the Shoot unless the user names it separately.
- **Project** — a DaVinci Resolve editing effort that may use footage from several Shoots.

If `v-flow` is not on PATH, install it before routing: `uv tool install vflow-cli`, or `pipx install vflow-cli` when uv is absent. Both give an isolated install; confirm with `v-flow --help`.

Route by the outcome the user wants:

- Set up drives or change where media lives: [references/setup.md](references/setup.md)
- Copy footage or photos from a camera card or received folder: [references/ingest.md](references/ingest.md)
- Put footage on an editing drive, edit from the Archive, or remove a temporary editing copy: [references/working-copies.md](references/working-copies.md)
- Save a finished video, graded clip, or Resolve project backup: [references/delivery.md](references/delivery.md)
- Back up an ordinary folder or copy files out of long-term storage: [references/backup-restore.md](references/backup-restore.md)
- Find possible duplicate files: [references/duplicates.md](references/duplicates.md)
- Add checksum coverage to archive folders that predate v-flow: [references/indexing.md](references/indexing.md)

Read the current branch's reference before acting. In a chained request, finish the current branch before reading the next branch's reference.

Resolve exact paths and identities before changing storage. Dry-run every changing command and obtain approval where the selected reference requires it.
