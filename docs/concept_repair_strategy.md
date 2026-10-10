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

## Auto-repair

Auto-repair is allowed only when:

- the mix is inconsistent
- the Kodi library no longer lists any of the mix's missing files
- a unique, high-confidence repair candidate is found

If the result is ambiguous, automatic repair must not guess.
