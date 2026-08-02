# Copy footage from a card or received folder

**Ingest** copies one received card or source folder into protected long-term storage while leaving the source unchanged.

The destination collection is a **Shoot**: footage captured in a certain date range and stored as one named collection. Each card or folder preserved during one ingest is an **Import Batch** inside that Shoot.

1. Resolve the exact card or source path and the Shoot name for the footage collection. Let v-flow derive a date-based name with `--auto` only when the user chooses that behavior.

   Ask for an Import Batch name only when the user needs an explicit card or batch identity. Otherwise let v-flow derive it. Use `--files` only when the user explicitly wants a subset.

   Complete when one source and one Shoot are unambiguous.

2. State that v-flow keeps the received folders and companion files together, records SHA-256 checksums, copies them to the Archive, leaves the source in place, and creates no editing copy.

3. Run one command:

   ```bash
   v-flow ingest --source <source> --shoot <shoot> [--import-batch <batch>]
   v-flow ingest --source <source> --auto [--import-batch <batch>]
   ```

   Complete when the CLI reports a completed Import Batch or names the safety check that failed.

4. Report where the footage is stored, how many files were copied or already verified, whether the manifest passed, and that the card or source remains unchanged.

   Complete when every failure has a concrete retry or inspection action.

## Safety gates

- Preserve the received folder structure and companion files.
- Use checksums, not filenames alone, as proof of file identity.
- Keep the card or source folder in place.
- Use Checkout when the user wants footage copied to an editing drive.
