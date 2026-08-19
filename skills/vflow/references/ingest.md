# Copy a card or received folder into long-term storage

**Ingest** copies one card or source folder into protected long-term storage while leaving the source unchanged. It reads the whole source once and routes by media kind: footage into a **Shoot**, photos and their editing sidecars into a **Collection**.

A Shoot is footage captured in a certain date range, held as one flat folder at `Video/RAW/<shoot>/`. A Collection is the matching group of photos, held as one flat folder at `Photo/RAW/<collection>/`. Each folder carries a hidden `.vflow-manifest.json` recording checksums and provenance, so duplicate detection is proof by content, never by filename. Several cards ingested under one name merge into the same flat folders; each card is recorded as its own **Import Batch** inside every manifest it writes.

1. Resolve the exact card or source path and the Shoot name. The Collection carries the Shoot name, so ask for `--collection` only when the user wants the photos under a different name. Let v-flow derive a date-based name for both with `--auto` only when the user chooses that behavior.

   Ask for an Import Batch name only when the user needs an explicit card identity. Otherwise let v-flow derive it. Use `--files` only when the user explicitly wants a subset; it selects across both kinds at once.

   Complete when one source and one Shoot are unambiguous.

2. State what lands where: footage files (video and audio) go straight into the Shoot folder, and photos go straight into the Collection folder with their editing sidecars (`.pp3`, `.xmp`) beside them — including when `--files` selects the photo. Camera sidecars, thumbnails, card databases, and hidden files stay on the card and are listed in a manifest with a reason. Offer `--include-all` when the user wants those files preserved too; they go into a hidden folder inside the Shoot so the Shoot folder itself stays flat.

   State that a card without footage creates no Shoot and a card without photos creates no Collection.

   State that v-flow records SHA-256 checksums while copying, verifies each archived file by re-reading it on the Archive, leaves the source in place, and creates no editing copy.

3. Run one command:

   ```bash
   v-flow ingest --source <source> --shoot <shoot> [--collection <collection>] [--files <pattern>] [--include-all]
   v-flow ingest --source <source> --auto [--include-all]
   ```

   Complete when the CLI reports each folder it wrote and its counts, or names the safety check that failed.

4. Report where the footage and the photos are stored, how many files of each kind were copied, already verified, deduplicated, and excluded, and that the card or source remains unchanged.

   Complete when every failure has a concrete retry or inspection action.

## Repeated and overlapping ingests

- Re-running the same ingest resumes from the manifests: files already archived and verified are not read from the card again.
- A clip whose content is already archived anywhere in `Video/RAW`, or a photo whose content is already archived anywhere in `Photo/RAW`, is skipped and recorded as deduplicated with a pointer to the existing file. Matching name and size alone never justifies a skip.
- A file that shares a name with different existing content lands with a suffix, such as `C6634_b.MP4`, and the manifest keeps its original name. A deduplicated photo's sidecars follow it to the copy it matched.

## Safety gates

- Use checksums, not filenames alone, as proof of file identity.
- Keep the card or source folder in place.
- Keep the Shoot and Collection folders flat and readable by any editing tool.
- Keep editing sidecars beside their photos wherever photos land.
- Keep Shoot and Collection names exactly as the user gave them.
- Use Checkout when the user wants footage copied to an editing drive.
