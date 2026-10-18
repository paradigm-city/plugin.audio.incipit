# Sidecar Metadata Concept

Sidecar metadata keeps saved mixes inspectable and repairable.

## Important sections

```json
{
  "seed": "...",
  "size": 25,
  "track_count": 25,
  "label": "...",
  "updated_ts": 1770000000,
  "unsaved": true,
  "saved_ts": 1770000000,
  "modified_ts": 1770000000,
  "cache_path": "...",
  "mix_parameters": {},
  "consistency": {},
  "repair_readiness": {},
  "discovery": {}
}
```

## Saving

`updated_ts` is when the mix was made; Saved mixes are ordered and grouped by it. `"unsaved": true` marks the current mix until the listener saves it; saving removes the key and records `saved_ts`, and `name` if the listener gave the mix a name of their own. See "The current mix and saved mixes" in `concept_overview.md`.

## Mix parameters

Mix generation parameters are recorded so a saved mix can later explain how it was created.

## Consistency

The consistency section describes missing files and when they were first detected.

## Repair readiness

The repair readiness section records whether repair is possible, why, and which missing files the Kodi music library still lists.

## Discovery relation

When a mix is generated from Discovery mode, the seed should be the captured Discovery song at the moment the user selected the action, not whatever happens to play later while the dialog is open.
