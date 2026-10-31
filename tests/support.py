"""Shared test setup: loads the add-on modules against the fake Kodi API."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
import unittest
from unittest import mock
from urllib.parse import parse_qsl, urlencode, urlsplit

import fake_kodi
from fake_kodi import ADDON_DIR, kodi
from fake_source import FakeSource

PLUGIN_URL = "plugin://plugin.audio.incipit/"
HANDLE = 7


def load_addon_module(name):
    fake_kodi.install()
    if ADDON_DIR not in sys.path:
        sys.path.insert(0, ADDON_DIR)

    # main.py reads the plugin URL and handle from sys.argv at import time.
    saved_argv = sys.argv
    sys.argv = [PLUGIN_URL, str(HANDLE), ""]
    try:
        return importlib.import_module(name)
    finally:
        sys.argv = saved_argv


main = load_addon_module("main")
service = load_addon_module("service")
context_mix = load_addon_module("context_mix")
context_radio = load_addon_module("context_radio")
logs = load_addon_module("logs")


def plugin_query(text):
    """Query parameters of a plugin:// URL, also inside RunPlugin(...) or Container.Update(...,replace)."""
    # urlencode() escapes "," and ")", so the URL ends at the first of them.
    match = re.search(r"plugin://[^,)\s]+", text)
    return dict(parse_qsl(urlsplit(match.group(0)).query)) if match else {}


class FakeClock:
    """Replaces time.time() so tests can step through excerpt lengths and grace periods."""

    def __init__(self, start=1_800_000_000.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class KodiTestCase(unittest.TestCase):
    def use_clock(self, start=1_800_000_000.0):
        clock = FakeClock(start)
        patcher = mock.patch("time.time", clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        return clock

    def setUp(self):
        kodi.reset()
        self.addCleanup(kodi.cleanup)
        # Never start the real Claude CLI from tests (it may be installed on the machine running them).
        patcher = mock.patch.object(main.mix_assist_claude, "find_cli", return_value="")
        patcher.start()
        self.addCleanup(patcher.stop)
        main.MIX_ASSIST_AVAILABLE.update(checked=0.0, found=False)
        main.PENDING_DIRECTORY_ITEMS.clear()

        main.LAST_MIX_GENERATION_PARAMS.clear()
        main.AUDIO_LIBRARY_FRESHNESS_CACHE = {"fetched_ts": 0, "payload": {}}
        main.KODI_MUSIC_TRACK_TEMPLATE_CACHE = None
        service.DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL = 0.0
        service.METADATA_REFRESH_PENDING_VIEW_REFRESH = False
        service.METADATA_REFRESH_LAST_SELECTION_TOKEN = ""
        service.METADATA_REFRESH_LAST_REFRESH_TS = 0
        service.LIBRARY_UPDATE.update(scan_finished=False, first_tick_ts=0.0, resume_checked=False)
        service.RADIO_TICK_SUMMARY["text"] = ""

        # Keep tests independent of the user's locale settings in Kodi.
        kodi.kodi_settings["musicfiles.trackformat"] = "[%N. ]%A - %T"

    def log_everything(self):
        """Every area's switch in Settings > Logging on."""
        kodi.settings.update({switch: "true" for switch in logs.AREAS.values()})

    # --- plugin --------------------------------------------------------------------------
    def run_plugin(self, **query):
        saved_argv = sys.argv
        sys.argv = [PLUGIN_URL, str(HANDLE), "?" + urlencode(query) if query else ""]
        try:
            main.router()
        finally:
            sys.argv = saved_argv

    def finish_listing(self):
        """Hand the entries added so far to the fake Kodi (as the end of a listing does)."""
        main.end_directory(HANDLE)

    def listed_labels(self):
        return [item.getLabel() for _url, item, _folder in kodi.directory_items]

    # --- saved mixes ---------------------------------------------------------------------
    def save_mix(self, tracks, seed=None, size=None, saved=True, **meta):
        """A new mix (the current mix), saved unless saved=False. Returns its file."""
        seed = seed if seed is not None else tracks[0]
        size = size if size is not None else len(tracks)
        cache_path = main.create_current_mix(seed, size, list(tracks))
        if saved:
            main.save_current_mix(cache_path)
        if meta:
            sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
            sidecar.update(meta)
            self.write_json(main.mix_meta_path_from_cache_path(cache_path), sidecar)
        return cache_path

    def current_mix_tracks(self):
        return main.load_mix_by_cache_path(main.get_current_mix_cache_path())

    def read_mix(self, cache_path):
        with open(cache_path, encoding="utf-8") as handle:
            return [line for line in handle.read().splitlines() if line.strip()]

    def read_json(self, path):
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def write_json(self, path, payload):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def profile_path(self, name):
        return os.path.join(kodi.profile_dir(), name)

    # --- assertions ----------------------------------------------------------------------
    def assertNotified(self, text):
        messages = kodi.notification_messages()
        self.assertTrue(any(text in message for message in messages), f"{text!r} not in notifications {messages!r}")

    def assertBuiltin(self, prefix):
        self.assertTrue(
            any(command.startswith(prefix) for command in kodi.builtins),
            f"No builtin starting with {prefix!r}; got {kodi.builtins!r}",
        )


class SourceTestCase(KodiTestCase):
    """Mixes come from a stand-in for the sound engine (fake_source.FakeSource), set per test with set_mix."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = FakeSource()

    def setUp(self):
        super().setUp()
        self.source.reset()
        patcher = mock.patch.object(main.soundprint, "neighbours", self.source.neighbours)
        patcher.start()
        self.addCleanup(patcher.stop)
