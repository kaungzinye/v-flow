# v-flow Media Lifecycle

v-flow preserves camera originals, places media for active editing, and retains exported videos without taking ownership of DaVinci Resolve's editing and grading model.

## Language

**Project**:
A creative editing effort that combines media from one or more Shoots and produces Final Videos. A Shoot can contribute media to multiple Projects.
_Avoid_: Job folder, shoot project

**Shoot**:
Footage captured in a certain date range and stored as one named collection. A Shoot contains one or more Import Batches and is independent of the Projects that use it.
_Avoid_: Project, day folder

**Import Batch**:
The immutable contents received from one camera card or source folder during a single ingest.
_Avoid_: Flattened import, loose clips

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
