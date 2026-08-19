# v-flow Media Lifecycle

v-flow preserves camera originals, places media for active editing, and retains exported videos without taking ownership of DaVinci Resolve's editing and grading model.

## Language

**Project**:
A creative editing effort that combines media from one or more Shoots and produces Final Videos. A Shoot can contribute media to multiple Projects.
_Avoid_: Job folder, shoot project

**Shoot**:
Footage captured in a certain date range and stored as one named collection, held as one flat folder under the configured footage root, `Video/RAW` by default. A Shoot receives one or more Import Batches and is independent of the Projects that use it.
_Avoid_: Project, day folder

**Import Batch**:
The media received from one camera card or source folder during a single ingest, recorded per file in every manifest that ingest writes. One card carrying both footage and photos records the same Import Batch into its Shoot Manifest and its Collection's manifest.
_Avoid_: Batch folder, card folder

**Shoot Manifest**:
The hidden `.vflow-manifest.json` inside a Shoot or Collection folder. It records the checksum algorithm and, per file, its name, byte size, checksum, card-relative path, Import Batch, and ingest time, plus the files excluded or deduplicated during ingest and the capture-date span its folder's contents cover.
_Avoid_: Sidecar, index

**Partial Shoot Manifest**:
A Shoot Manifest marked `"partial": true`, holding checksums for some of its folder's files while the rest stay unrecorded. Ingest writes one when a size match on an unindexed folder makes it hash a candidate file, so that file is never hashed again.
_Avoid_: Draft manifest, incomplete index

**Indexing**:
Hashing the files already sitting in a Shoot or Collection folder to give it a complete Shoot Manifest. Indexing is explicitly invoked, adds only the hidden manifest, moves and renames nothing, and leaves the folder's visible contents byte-for-byte identical. Entries it writes carry `"source": "indexed-in-place"` instead of Import Batch provenance.
_Avoid_: Scan, import, migration

**Collection**:
A freely named group of photos held as one flat folder under the configured photo root, `Photo/RAW` by default, together with their editing sidecars and a Shoot Manifest. A Collection takes the name of the Shoot its card fed, and an explicit Collection name overrides that. A Collection is its own folder with its own manifest, so it stands on its own where no footage exists, and v-flow never renames one.
_Avoid_: Photo shoot, album, day folder

**Camera Original**:
Unmodified source media together with its companion metadata, audio, proxy, and sidecar files.
_Avoid_: RAW when the camera format is not raw

**Archive**:
Protected retained storage. Archiving copies an asset into the Archive and verifies the copy; it never moves or deletes the original location.
_Avoid_: Backup-and-delete, cold storage

**Working Copy**:
An optional copy of archived media placed on a laptop or work drive for active editing. It is removable after the Archive and Resolve safety gates pass.
_Avoid_: Master, archive copy

**Direct Archive Access**:
Editing Camera Originals in place from the Archive without creating a Working Copy.
_Avoid_: Checkout

**Checkout**:
The creation of a Working Copy from archived media at an explicitly chosen working location.
_Avoid_: Restore, move

**Final Video**:
A completed edited timeline export retained as a project output.
_Avoid_: Graded Select, scratch render

**Graded Select**:
A manually chosen source clip exported with its Resolve grade baked in for viewing or reuse.
_Avoid_: Final Video, automated rendition

**Project Backup**:
A portable snapshot of Resolve project state that preserves timelines, edits, and grades without owning the Camera Originals.
_Avoid_: Project Library, media archive

**Finish**:
The state in which a Project has a verified Project Backup and its retained outputs are archived. Finish does not remove local files.
_Avoid_: Cleanup, archive

**Cleanup**:
An explicit removal of eligible non-archive copies after archive verification, Resolve validation by default, and user confirmation.
_Avoid_: Archive, finish

**Restore**:
The creation of a new copy from the Archive at a chosen destination without changing the archived asset.
_Avoid_: Checkout when the destination is an active media workspace
