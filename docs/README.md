# Incipit Documentation

This folder contains the concept documentation and flow diagrams for Incipit, the Kodi add-on formerly called
MusicIP (its ID is `plugin.audio.incipit`, until 2026-10-29 `plugin.audio.musicip`).

Current documentation baseline: **1.0.88**  
Feature baseline: **1.0.87**

## Documents

- `concept_incipit.md`: **how mixes are made and kept now**: Source (the sound engine), Character, Intent
- `concept_overview.md`
- `concept_discovery_mode.md`
- `concept_radio_mode.md`
- `concept_repair_strategy.md`
- `concept_sidecar_metadata.md`
- `concept_ai_mix_assist.md`: background: how the checks (then AI Mix Assist) were developed and calibrated
- `glossary_ai_mix_assist.md`: terms, with today's names and the retired ones
- `concept_suggestion_engine.md`: background: how MusicIP came to be replaced by the sound engine
- `plan_addon_id_change.md`: **open**: changing the add-on's ID to `plugin.audio.incipit` (prepared, not started)
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
