# Mix Consistency and Repair Concept

## Problem

Saved mixes reference file paths. Those files may later be moved, renamed, deleted, or changed outside Kodi.

This causes storage-level inconsistency: the saved mix contains missing file paths.

## Consistency sidecar

Each saved mix has sidecar metadata. The consistency section records:

- current consistency status
- check timestamp
- missing files
- first missing timestamp per track
- first inconsistent timestamp
- last inconsistency change timestamp
- missing signature

## Repair readiness

Repair candidates come from the Kodi music library, so the library must already reflect the moved or deleted files.

For every missing file of the mix, the readiness check asks the Kodi library whether it still lists that exact file:

- If the library no longer lists any of them, it has caught up with the change: repair is **ready**.
- If it still lists some, the library has not been updated and cleaned since the files disappeared: the add-on offers **Update library before repair** and names the files.
- If the library cannot be queried, repair is not offered.

Earlier versions compared Kodi's library timestamps with the time the add-on detected the missing files. That could block repair indefinitely: when the library was updated before the check noticed the missing files, later scans changed nothing and the timestamps never moved (finding F9).

## Music sources

Kodi cannot know where a missing file has moved, and some folders are left out of the library on purpose. Two checks help after a reorganization of the folders on disk:

- **Source no longer available:** if the music source that covered a missing file's old location no longer exists (or its drive or share is offline), repair is not offered ("Check music sources before repair"); scanning cannot help until the sources match the folders on disk. A missing file outside all sources is only reported: that is also the normal state after an obsolete source was removed.
- **Missing file found elsewhere:** the background consistency check searches the disks for missing files. It builds one virtual library root per disk, share or root folder (the deepest folder containing all of its music sources), walks it, and matches file name plus folder name. It skips music sources that have songs in the library; a configured source without any library songs was never scanned into the library and is searched like any other folder. The search runs only when a mix's missing files change or after a day, stops after 60 seconds, and waits while Discovery mode is active.
  - Found **outside every music source**: a notification says where. Whether to add that location to the library is the user's decision, since some folders are left out on purpose; repair is never blocked by it.
  - Found **in a source that was never scanned**: a notification says which source, and repair readiness becomes **Scan music source before repair**. That context menu entry asks whether to scan the source into the library and starts the scan. Since the track was in the library before, this is usually wanted. Readiness checks the source live, so it clears as soon as the source has songs in the library.

## Auto-repair

Auto-repair is allowed only when:

- the mix is inconsistent
- the Kodi library no longer lists any of the mix's missing files
- a unique, high-confidence repair candidate is found

If the result is ambiguous, automatic repair must not guess.
