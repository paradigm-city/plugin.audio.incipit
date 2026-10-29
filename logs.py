# -*- coding: utf-8 -*-
"""Logging by area, shared by the plugin and the service.

Settings > Logging has a switch per area: General, Mixing, AI Mix Assist, Radio, Discovery mode and Saved-mix
checks. With an area's switch on, its detailed messages go to kodi.log; errors and warnings always do. Every line
names its area, e.g. "[plugin.audio.incipit] [radio] Radio mode: ...", so one area can be read on its own.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ElementTree

import xbmc
import xbmcaddon
import xbmcvfs

# The add-on's ID, the one place every module takes it from; until 2026-10-29 plugin.audio.musicip (service.py
# takes the data of that ID over once, take_over_old_data).
ADDON_ID = "plugin.audio.incipit"
ADDON = xbmcaddon.Addon(ADDON_ID)

# area -> its switch in Settings > Logging
AREAS = {
    "general": "log_general",
    "mixing": "log_mixing",
    "ai": "log_ai",
    "radio": "log_radio",
    "discovery": "log_discovery",
    "checks": "log_checks",
}
# Until October 2026 there was one switch for the plugin and one for the service.
OLD_SWITCHES = ("plugin_extended_logging", "service_extended_logging")
MIGRATED_MARKER = "logging_switches_migrated"


def enabled(area: str) -> bool:
    try:
        return ADDON.getSetting(AREAS[area]).strip().lower() == "true"
    except Exception:
        return False


def describe_switches() -> str:
    """For the service's start line, e.g. "general on, mixing off, ..."."""
    return ", ".join(f"{area} {'on' if enabled(area) else 'off'}" for area in AREAS)


def write(area: str, message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    """Errors, warnings and messages marked always are written in any case; the rest when the area is on, then at
    least as LOGINFO (Kodi drops LOGDEBUG unless its own debug logging is on)."""
    if level >= xbmc.LOGWARNING or always:
        xbmc.log(f"[{ADDON_ID}] [{area}] {message}", level)
    elif enabled(area):
        xbmc.log(f"[{ADDON_ID}] [{area}] {message}", max(level, xbmc.LOGINFO))


def log_general(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("general", message, level, always)


def log_mixing(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("mixing", message, level, always)


def log_ai(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("ai", message, level, always)


def log_radio(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("radio", message, level, always)


def log_discovery(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("discovery", message, level, always)


def log_checks(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    write("checks", message, level, always)


def migrate_old_switches() -> bool:
    """Once: if one of the old switches was on, turn every area on. Kodi keeps the old values in the add-on's
    settings.xml after they are no longer declared. Returns whether the areas were turned on."""
    profile = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    marker = os.path.join(profile, MIGRATED_MARKER)
    if os.path.exists(marker):
        return False
    turned_on = False
    try:
        stored = ElementTree.parse(os.path.join(profile, "settings.xml")).getroot()
        old = {node.get("id"): (node.text or "").strip().lower() for node in stored.iter("setting")}
        if any(old.get(switch) == "true" for switch in OLD_SWITCHES):
            for switch in AREAS.values():
                ADDON.setSettingBool(switch, True)
            turned_on = True
    except (OSError, ElementTree.ParseError):
        pass
    try:
        os.makedirs(profile, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("1\n")
    except OSError:
        pass
    return turned_on
