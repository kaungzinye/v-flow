# Put footage on an editing drive or free that space

A **Working Copy** is a temporary, verified copy of archived footage on a laptop or SSD. **Checkout** creates it; **Cleanup** removes it.

## Put footage on a laptop or SSD

1. Resolve which Shoot the user means and where they want to edit.

   Offer two choices:
   - copy the footage to a configured laptop or SSD;
   - edit directly from the Archive without creating another copy.

   Introduce these as Checkout to a named Working Location and Direct Archive Access. Complete when exactly one choice is explicit.

2. For a Working Copy, preview first:

   ```bash
   v-flow checkout --shoot <shoot> --working-location <name> --dry-run
   ```

   Summarize verification, conflicts, required space, and destination. After approval, run the same command without `--dry-run`.

   For editing directly from long-term storage, run:

   ```bash
   v-flow checkout --shoot <shoot> --direct-archive-access
   ```

   Complete when the CLI reports a verified Working Copy or the Archive paths to edit from.

3. Report the active editing path and the protected Archive path separately.

## Remove temporary editing footage

1. Confirm that the target is a Checkout-created Working Copy, not the Archive. Resolve its Shoot, named Working Location, and Resolve Project.

2. Explain that Cleanup first verifies the Archive copy and checks whether Resolve still depends on the temporary files. Preview every check:

   ```bash
   v-flow cleanup --shoot <shoot> --working-location <name> --project <project> --dry-run
   ```

   Complete when Archive checksums pass and Resolve media is confirmed or listed for relinking.

3. Summarize the Resolve effects and exact files planned for deletion. After approval, run the same command without `--dry-run` and let the CLI request final confirmation.

   Complete when deleted and failed counts account for every planned file.

Use `--skip-resolve-validation` only when the user explicitly accepts that one risk. Archive verification and final confirmation still apply.

## Safety gates

- Keep Archive contents in place.
- Stop Checkout on a content conflict or insufficient drive capacity.
- Stop Cleanup on an Archive target, checksum failure, unresolved Resolve media, unavailable Resolve, or declined confirmation.
