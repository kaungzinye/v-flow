# Find possible duplicate files

This command is an inspection tool. It does not delete anything.

1. Ask where to look: long-term Archive storage, the configured laptop location, or both. Ask whether the user wants all files or only a recent time window.

   Complete when the scan boundary is explicit.

2. Run:

   ```bash
   v-flow list-duplicates --location <archive|laptop|both> [--past-hours <hours>]
   ```

   Complete when the possible duplicate groups and their paths are available for review.

3. Report the number of groups, number of extra copies, scan scope, and representative paths. Explain that v-flow identifies these candidates by matching filename and size; that is useful evidence but not proof that deletion is safe.

Complete when the user can inspect every candidate without a storage change.

If the user wants to free space, determine whether the target is a temporary Working Copy created by Checkout. If so, use Cleanup. Keep Archive files and untracked folders read-only.
