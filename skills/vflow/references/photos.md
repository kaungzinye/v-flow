# Copy photos from a card or folder

**photo-ingest** copies photos from one card or source folder into a **Collection** — a freely named flat folder under `Photo/RAW` — while leaving the source unchanged. Each Collection carries a hidden Shoot Manifest with per-file checksums, so duplicate detection is proof by content, never by filename.

1. Resolve the source path and the Collection name. Collections are named by event or trip, are independent of footage Shoots, and v-flow never renames one. Use `--files` only when the user explicitly wants a subset.

   Complete when one source and one Collection are unambiguous.

2. State what lands where: photos go flat into the Collection, and their editing sidecars (`.pp3`, `.xmp`) ride along beside them automatically — including when `--files` selects the photo. Every other file stays on the card and is listed in the manifest with a reason.

   State that v-flow records checksums while copying, verifies each archived file by re-reading it on the Archive, skips a photo only when its content is already archived, and leaves the source in place.

3. Run one command:

   ```bash
   v-flow photo-ingest --source <source> --collection <collection> [--files <pattern>]
   ```

   Complete when the CLI reports the Collection and its counts, or names the safety check that failed.

4. Report where the photos are stored, how many files were copied, already verified, deduplicated, and excluded, and that the card or source remains unchanged.

   Complete when every failure has a concrete retry or inspection action.

## Safety gates

- Use checksums, not filenames alone, as proof of file identity.
- Keep the card or source folder in place.
- Keep editing sidecars beside their photos wherever photos land.
- Keep Collection names exactly as the user gave them.
