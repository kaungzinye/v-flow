# Copy footage from a card or received folder

**Ingest** copies footage from one card or source folder into protected long-term storage while leaving the source unchanged.

The destination collection is a **Shoot**: footage captured in a certain date range and stored as one named collection. Footage lands flat in `Video/RAW/<shoot>/`, next to a hidden `.vflow-manifest.json` that records checksums and provenance. Several cards ingested into one Shoot merge into the same flat folder; each card is recorded as its own **Import Batch** inside the manifest.

1. Resolve the exact card or source path and the Shoot name for the collection. Let v-flow derive a date-based name with `--auto` only when the user chooses that behavior.

   Ask for an Import Batch name only when the user needs an explicit card identity. Otherwise let v-flow derive it. Use `--files` only when the user explicitly wants a subset.

   Complete when one source and one Shoot are unambiguous.

2. State what lands where: footage files (video and audio) go straight into the Shoot folder; camera sidecars, thumbnails, card databases, and hidden files stay on the card and are listed in the manifest with a reason. Offer `--include-all` when the user wants those files preserved too; they go into a hidden folder inside the Shoot so the Shoot folder itself stays flat.

   State that v-flow records SHA-256 checksums while copying, verifies each archived file by re-reading it on the Archive, leaves the source in place, and creates no editing copy.

3. Run one command:

   ```bash
   v-flow ingest --source <source> --shoot <shoot> [--include-all]
   v-flow ingest --source <source> --auto [--include-all]
   ```

   Complete when the CLI reports the Shoot folder and its counts, or names the safety check that failed.

4. Report where the footage is stored, how many files were copied, already verified, deduplicated, and excluded, and that the card or source remains unchanged.

   Complete when every failure has a concrete retry or inspection action.

## Repeated and overlapping ingests

- Re-running the same ingest resumes from the manifest: files already archived and verified are not read from the card again.
- A clip whose content is already archived anywhere in `Video/RAW` is skipped and recorded as deduplicated with a pointer to the existing file. Matching name and size alone never justifies a skip.
- A clip that shares a name with a different existing clip lands with a suffix, such as `C6634_b.MP4`, and the manifest keeps its original name.

## Safety gates

- Use checksums, not filenames alone, as proof of file identity.
- Keep the card or source folder in place.
- Keep the Shoot folder flat and readable by any editing tool.
- Use Checkout when the user wants footage copied to an editing drive.
