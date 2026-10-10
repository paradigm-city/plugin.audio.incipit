# MusicIP Add-on Documentation

This folder contains the current concept documentation and flow diagrams for the MusicIP Kodi add-on.

Current documentation baseline: **1.0.88**  
Feature baseline: **1.0.87**

## Documents

- `concept_overview.md`
- `concept_discovery_mode.md`
- `concept_repair_strategy.md`
- `concept_sidecar_metadata.md`
- `testing_quality_notes.md`
- `findings.md`: known problems in the code and their status

## Flow diagrams

Mermaid source files and PNG exports are in `diagrams/`.

- `discovery_mode_flow.mmd`
- `discovery_mode_flow.png`
- `discovery_service_state_flow.mmd`
- `discovery_service_state_flow.png`
- `playlist_buffer_flow.mmd`
- `playlist_buffer_flow.png`
- `repair_readiness_flow.mmd`
- `repair_readiness_flow.png`
- `mix_generation_flow.mmd`
- `mix_generation_flow.png`

Note: PNG rendering depends on the local build environment. If Mermaid CLI is unavailable, the PNG export contains a readable source-rendered diagram snapshot. The `.mmd` files remain the authoritative Mermaid source.
