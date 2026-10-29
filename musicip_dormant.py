"""MusicIP as the add-on's suggestion engine: dormant since 2026-10-29, when the sound engine (soundprint/) became the
only source of mixes. Nothing imports this file; it keeps the MusicIP code in one place, should it be needed again.

What it did: the MusicIP server (MusicIP Mixer, its web interface on port 10002) made a mix for a seed song through
/api/mix, with MusicIP's own parameters on top of the add-on's (style 0 to 200 and a filter defined in MusicIP;
variety and the artist reject size are the sound engine's too). The service asked MusicIP to reload its library
(/server/reload) after Kodi's music library scan and every 8 hours, but never while Radio or Discovery played.

To bring it back:
- settings.xml: a category "General" with the group "MusicIP server" (host: string, default localhost; port:
  integer, default 10002; timeout: integer, default 10 seconds), in Mixing "mix_style_preference" (integer 0 to 10,
  default 2) and "mix_filter" (string), and in the sound engine's category "suggestion_engine" (0 MusicIP, 1 the
  sound engine). Their texts were strings 30100 to 30107, 30304/30305, 30308/30309 and 30801 to 30805.
- main.fetch_mix: call fetch_musicip_mix below instead of main.fetch_sound_mix when MusicIP is chosen, and give
  get_effective_mix_parameters the style and filter again (style_parameters).
- service.run_library_update_tick: run run_musicip_reload_tick below instead of the sound engine's analysis.
- tests: tests/fake_musicip.py (a local HTTP server standing in for MusicIP), test_main_musicip_client.py and
  test_service_musicip_reload.py, in git history before the commit that made this file.

The functions take the plugin module (main.py) as `plugin` for the settings, logging and helpers they use, and the
service module as `service` for its state files, so they can be called again without being moved back.
"""

from __future__ import annotations

import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote_from_bytes, urlencode
from urllib.request import urlopen

import xbmc


# --- Settings ---------------------------------------------------------------------------------------------------------
def get_server_host(plugin) -> str:
    return plugin.get_setting("host", "localhost").strip() or "localhost"


def get_server_port(plugin) -> int:
    return plugin.get_setting_int("port", 10002)


def get_timeout(plugin) -> int:
    timeout = plugin.get_setting_int("timeout", 10)
    return max(1, timeout)


def get_mix_style_preference(plugin) -> int:
    value = plugin.get_setting_int("mix_style_preference", 2)
    return max(0, min(10, value))


def get_mix_style_label(plugin, value: int | None = None) -> str:
    raw_value = get_mix_style_preference(plugin) if value is None else int(value)
    ui_value = max(0, min(10, raw_value))
    labels = {
        0: "ignore",
        1: "barely noticeable",
        2: "weak preference",
        3: "light preference",
        4: "mild preference",
        5: "medium preference",
        6: "balanced preference",
        7: "clear preference",
        8: "strong preference",
        9: "very strong preference",
        10: "strongly prefer",
    }
    return labels.get(ui_value, f"{ui_value}/10")


def get_mix_filter(plugin) -> str:
    return plugin.get_setting("mix_filter", "").strip()


def style_parameters(plugin) -> dict:
    """MusicIP's own mix parameters, to add to main.get_effective_mix_parameters."""
    # MusicIP API style range: 0..200. UI scale: 0..10 in steps of 1.
    style_ui = get_mix_style_preference(plugin)
    return {"style": style_ui * 20, "style_ui": style_ui, "style_label": get_mix_style_label(plugin, style_ui),
            "filter": get_mix_filter(plugin)}


# --- A mix ------------------------------------------------------------------------------------------------------------
def build_musicip_parameter_query(plugin, seed_song: str, params: dict) -> str:
    # MusicIP on Windows expects the seed path in the Windows code page (cp1252), which also has œ, ’, “ ”, – and …
    encoded_seed = quote_from_bytes(seed_song.encode("cp1252", errors="replace"))

    query_params = {
        "size": str(int(params.get("size") or plugin.get_playlist_size())),
        "sizeType": "tracks",
        "style": str(max(0, min(200, int(params.get("style") or 0)))),
        "variety": str(int(params.get("variety") or 0)),
        "mixgenre": "false",
        "content": "text",
    }

    filter_value = str(params.get("filter") or "").strip()
    if filter_value:
        query_params["filter"] = filter_value

    reject_size = int(params.get("rejectsize") or 0)
    if reject_size > 0:
        query_params["rejectsize"] = str(reject_size)
        query_params["rejectType"] = "tracks"

    return f"song={encoded_seed}&{urlencode(query_params)}"


def build_musicip_url(plugin, seed_song: str, size: int, mix_params: dict | None = None) -> str:
    params = mix_params or plugin.get_effective_mix_parameters(size_override=size)
    query = build_musicip_parameter_query(plugin, seed_song, params)
    return f"http://{get_server_host(plugin)}:{get_server_port(plugin)}/api/mix?{query}"


def decode_response(data: bytes) -> str:
    for enc in ("utf-8", "iso-8859-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def fetch_musicip_mix(plugin, seed_song: str, size: int, params: dict, progress=None) -> list[str]:
    """MusicIP's mix for a seed, the seed first. progress(percent, text), if given, is told about each step."""
    if progress:
        progress(15, "MusicIP is mixing")
    url = build_musicip_url(plugin, seed_song, size, params)
    timeout = get_timeout(plugin)
    log_mixing = plugin.log_mixing

    try:
        encoded_seed = url.split("song=", 1)[1].split("&", 1)[0]
    except Exception:
        encoded_seed = ""

    log_mixing(f"MusicIP mix request: seed {seed_song!r} (encoded {encoded_seed!r}), size {size}, "
               f"parameters {params!r}, timeout {timeout} s, URL {url!r}")

    started = time.time()
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        try:
            error_body = exc.read()
        except Exception:
            error_body = b""

        log_mixing(f"MusicIP HTTP error {exc.code}", xbmc.LOGERROR)
        log_mixing(f"MusicIP error URL: {url!r}", xbmc.LOGERROR)
        log_mixing(f"MusicIP error seed raw: {seed_song!r}", xbmc.LOGERROR)
        log_mixing(f"MusicIP error seed encoded: {encoded_seed!r}", xbmc.LOGERROR)
        log_mixing(f"MusicIP error playlist size: {size}", xbmc.LOGERROR)
        log_mixing(f"MusicIP error body: {error_body!r}", xbmc.LOGERROR)
        raise plugin.MusicIPError(f"MusicIP server returned HTTP {exc.code}.") from exc
    except URLError as exc:
        log_mixing(f"MusicIP URL error for {url!r}: {exc}", xbmc.LOGERROR)
        raise plugin.MusicIPError(f"Could not reach MusicIP server at {get_server_host(plugin)}:"
                                  f"{get_server_port(plugin)}.") from exc
    except Exception as exc:
        log_mixing(f"MusicIP request failed for {url!r}: {exc}", xbmc.LOGERROR)
        raise plugin.MusicIPError(f"MusicIP request failed: {exc}") from exc

    text = decode_response(body)
    tracks = [line.strip() for line in text.splitlines() if line.strip()]
    log_mixing(f"MusicIP answered in {time.time() - started:.1f} s with {len(tracks)} song(s) for {seed_song!r}"
               + "".join(f"\n  {number}. {track}" for number, track in enumerate(tracks, start=1)))
    if not tracks:
        raise plugin.MusicIPError("MusicIP returned an empty mix.")

    return plugin.prepend_seed_track(seed_song, tracks)


# --- MusicIP's library: reloaded now and then in the background (not before every mix, which only made mixes
# slower), and after Kodi's music library scan, so songs new to Kodi's library also reach the mixes. A reload scans
# the music folders and takes in new songs, one at a time, minutes each, and MusicIP mixes little else meanwhile:
# so not while Radio or Discovery plays (they need its mixes; the reload waits until they stop), and a reload that
# doesn't answer in time is taking in songs (it goes on), not a failure. In a thread: the service loop must not wait.
# The service's LIBRARY_UPDATE holds scan_finished and first_tick_ts (shared with the sound engine's analysis).

MUSICIP_RELOAD_INTERVAL_SECONDS = 8 * 3600  # about three times a day
MUSICIP_RELOAD_RETRY_SECONDS = 30 * 60      # after a failed reload (MusicIP not running)
MUSICIP_RELOAD_MIN_TIMEOUT_SECONDS = 120
MUSICIP_RELOAD = {"thread": None}


def musicip_reload_state_path(service) -> str:
    return os.path.join(service.get_profile_dir(), "musicip_reload.json")


def reload_musicip_library(service, reason: str) -> bool:
    """Ask MusicIP to reload its library (/server/reload). The time is kept, so a Kodi restart doesn't reload
    again; a failure is retried later."""
    plugin = service.load_plugin_module()
    log_general = service.log_general
    url = f"http://{get_server_host(plugin)}:{get_server_port(plugin)}/server/reload"
    started = time.time()
    record = service.load_json_file(musicip_reload_state_path(service))
    try:
        with urlopen(url, timeout=max(MUSICIP_RELOAD_MIN_TIMEOUT_SECONDS, get_timeout(plugin))) as response:
            response.read()
    except TimeoutError:  # connected, no answer yet: MusicIP is taking in new songs
        service.save_json_file(musicip_reload_state_path(service), {"last_ts": int(time.time())})
        log_general(f"MusicIP library reload ({reason}): MusicIP is taking in new songs (no answer after "
            f"{time.time() - started:.0f} s); it goes on by itself.", always=True)
        return True
    except Exception as exc:
        log_general(f"MusicIP library reload ({reason}) failed for {url!r}: {exc}", xbmc.LOGWARNING, always=True)
        service.save_json_file(musicip_reload_state_path(service), dict(record, failed_ts=int(time.time())))
        return False
    service.save_json_file(musicip_reload_state_path(service), {"last_ts": int(time.time())})
    log_general(f"MusicIP library reloaded ({reason}) in {time.time() - started:.1f} s.", always=True)
    return True


def musicip_reload_due(service, now: float) -> str:
    """Why MusicIP's library should be reloaded now ("" if not): Kodi's music library scan has finished, or the
    last reload is MUSICIP_RELOAD_INTERVAL_SECONDS ago; never while Radio or Discovery plays."""
    if service.radio_is_active() or service.load_discovery_state().get("enabled"):
        return ""
    if service.LIBRARY_UPDATE["scan_finished"]:
        return "after Kodi's library scan"
    if now - service.LIBRARY_UPDATE["first_tick_ts"] < service.LIBRARY_UPDATE_STARTUP_DELAY_SECONDS:
        return ""
    record = service.load_json_file(musicip_reload_state_path(service))
    if now - int(record.get("failed_ts") or 0) < MUSICIP_RELOAD_RETRY_SECONDS:
        return ""
    return "scheduled" if now - int(record.get("last_ts") or 0) >= MUSICIP_RELOAD_INTERVAL_SECONDS else ""


def run_musicip_reload_tick(service) -> threading.Thread | None:
    """Start a background reload of MusicIP's library when one is due (not while one runs). Returns its thread."""
    now = time.time()
    if not service.LIBRARY_UPDATE["first_tick_ts"]:
        service.LIBRARY_UPDATE["first_tick_ts"] = now
    thread = MUSICIP_RELOAD["thread"]
    if thread is not None and thread.is_alive():
        return None
    reason = musicip_reload_due(service, now)
    if not reason:
        return None
    service.LIBRARY_UPDATE["scan_finished"] = False
    thread = threading.Thread(target=reload_musicip_library, args=(service, reason), name="MusicIP reload",
                              daemon=True)
    MUSICIP_RELOAD["thread"] = thread
    thread.start()
    return thread
