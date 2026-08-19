# Add checksum coverage to existing archive folders

Folders ingested by v-flow carry a Shoot Manifest from the start. Folders that predate v-flow have none, so checksum verification cannot vouch for them. **Indexing** hashes their files where they sit and writes the manifest — it moves nothing, renames nothing, and adds one hidden file per folder.

Indexing walks the flat folders under the configured footage and photo roots, `Video/RAW` and `Photo/RAW` by default; [setup.md](setup.md) covers changing them.

Ingest already handles look-alike candidates in unindexed folders on its own, one file at a time. Run a full index when the user wants whole-archive coverage: trustworthy card verification, or a duplicate sweep across old folders.

1. Preview the work first:

   ```bash
   v-flow index --all --dry-run
   ```

   Complete when the user has seen the folder count and total bytes to read, and understands the drive will be read for that long.

2. Run the index, for everything or one folder at a time:

   ```bash
   v-flow index --all
   v-flow index --folder <name>
   ```

   An interrupted run resumes where it stopped. A **Partial Shoot Manifest** — progress left by ingest's targeted hashing or an interrupted index — is completed without re-reading its verified files.

   Complete when the CLI reports each folder's manifest as complete.

3. Report how many folders gained complete manifests and note that the folders' visible contents are untouched.

## Safety gates

- Run indexing only when the user asks for it; never schedule it or start it as a side effect.
- Treat a partial manifest as incomplete coverage: it feeds duplicate detection, but it never supports a claim that a folder is fully verified.
- Keep the Archive read-only during indexing apart from the hidden manifest files.
