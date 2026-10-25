"""Write resources/settings.xml (Kodi's settings format version 1, with help texts) and the English strings.po.
usage: python tools/make_settings.py <addon dir> [--with-ai]
String ids are fixed per category (blocks of 100), so they stay the same on every branch. A category has groups,
each with an optional heading."""
import pathlib
import sys
from xml.sax.saxutils import escape, quoteattr

root = pathlib.Path(sys.argv[1])
WITH_AI = "--with-ai" in sys.argv

OPENNESS = ["Focused", "Close", "Balanced", "Open", "Adventurous"]
PERSPECTIVES = ["Mixed", "Technical", "Emotional", "Cultural", "Functional", "Lyrical"]  # main.PERSPECTIVE_LABELS
PERSPECTIVE_HELP = ("Mixed: the music's intention and its qualities together, the tested default. Technical: how it "
                    "is made (harmony, rhythm, form, musicianship), as a musician hears it. Emotional: the emotion "
                    "the artist sets out to express, and how seriously it is meant. Cultural: where it comes from (scene, era, tradition). Functional: what "
                    "it is for (a party, a drive, focus, falling asleep). Lyrical: what the words are about; for "
                    "instrumental music, the story it suggests.")

GENERAL = ("general", 30100, "General", [
    ("MusicIP server", [
        dict(id="host", type="text", default="localhost", label="Host",
             help="Name or address of the computer that runs the MusicIP server. \"localhost\" when it runs on this "
                  "computer."),
        dict(id="port", type="number", default="10002", label="Port",
             help="Port of the MusicIP server's web interface. MusicIP's default is 10002."),
        dict(id="timeout", type="number", default="10", label="HTTP timeout (seconds)",
             help="How long to wait for the MusicIP server to answer. Raise it if large mixes or a busy server cause "
                  "time-outs."),
    ]),
])
MIX = ("mix", 30300, "Mixing", [
    ("Mix parameters", [
        dict(id="playlist_size", type="slider", default="20", range=(1, 1, 100), label="Mix size (tracks)",
             help="How many tracks a new mix has. \"More like this\" and \"Less like this\" change a mix by a fifth "
                  "of this number."),
        dict(id="mix_style_preference", type="slider", default="2", range=(0, 1, 10),
             label="Style preference (0 ignore, 10 strongly prefer)",
             help="How strongly MusicIP favours tracks in the seed's style. 0 ignores style; 10 strongly prefers it."),
        dict(id="mix_variety", type="slider", default="0", range=(0, 1, 9), label="Variety",
             help="How far MusicIP may reach from the seed. 0 keeps a mix close to the seed's sound; 9 gives the "
                  "widest choice."),
        dict(id="mix_filter", type="text", default="", label="MusicIP filter",
             help="Name of a filter defined in MusicIP, for example to leave out certain genres. Empty: no filter."),
        dict(id="mix_reject_size", type="slider", default="0", range=(0, 1, 20),
             label="Do not repeat artist within this many tracks",
             help="Keeps an artist from appearing again within this many tracks. 0 allows repeats."),
    ]),
    ("Saved mixes", [
        dict(id="consistency_enabled", type="bool", default="true", label="Enable saved-mix consistency service",
             help="Regularly checks saved mixes for files that were moved or deleted, and marks the mixes affected "
                  "with a red \"!\"."),
        dict(id="consistency_interval_minutes", type="number", default="60", label="Check interval (minutes)",
             help="How often the consistency check runs."),
        dict(id="service_auto_repair_enabled", type="bool", default="false", label="Enable automatic mix repair",
             help="Replaces missing files in saved mixes on its own when the library has a safe match (the same "
                  "song, moved or re-tagged). Uncertain cases are left for \"Auto-repair this mix\" in the mix's "
                  "context menu."),
    ]),
])
AI = ("assist", 30400, "AI Mix Assist", [
    ("Mixes", [
        dict(id="mix_assist_auto_new_mixes", type="bool", default="true", label="Keep new mixes on track",
             help="After a new mix is created, AI Mix Assist checks it in the background and replaces tracks that "
                  "don't fit what the mix is about. A progress bar shows the steps; the changes are in the mix history "
                  "and can be undone. Needs the Claude Code CLI."),
        dict(id="mix_assist_auto_more_like_this", type="bool", default="true", label="Keep \"More like this\" on track",
             help="Before \"More like this\" inserts tracks, AI Mix Assist checks MusicIP's suggestions against the "
                  "song you selected and inserts only those that clearly fit. Takes up to a minute."),
        dict(id="mix_assist_mix_strictness", type="enum", default="2", label="Mix openness", options=OPENNESS,
             help="How much variety a mix welcomes when AI Mix Assist checks a new mix, tidies one up or adds tracks "
                  "with \"More like this\". Focused stays with the heart of the mix's style; Adventurous welcomes wide "
                  "variation, including tracks the AI calls borderline. Balanced is the tested default."),
        dict(id="mix_assist_mix_perspective", type="enum", default="0", label="Mix perspective", options=PERSPECTIVES,
             help="From which point of view AI Mix Assist works out what a mix is about and judges its tracks. "
                  + PERSPECTIVE_HELP + " A mix can have its own, in its \"AI Mix Assist...\" menu."),
        dict(id="mix_assist_name_mixes", type="bool", default="true", label="Name mixes and stations",
             help="At its first check, AI Mix Assist gives a mix or radio station a short name of 2 to 4 words "
                  "saying what it is about, like \"Cosmic Analog Journeys\". It is shown instead of the seed song and "
                  "suggested when you save a mix; a mix can be renamed in its \"AI Mix Assist...\" menu. Off: mixes "
                  "and stations are named after their seed song, unless you name them yourself."),
    ]),
    ("Claude Code", [
        dict(id="mix_assist_cli_path", type="text", default="", label="Claude Code CLI (empty: find it automatically)",
             help="Full path to the Claude Code program (claude.exe). Leave empty to find it automatically, for "
                  "example in the VS Code extension. AI Mix Assist uses your claude.ai subscription through it."),
        dict(id="mix_assist_statistics", type="action", label="Show statistics",
             data="RunPlugin(plugin://plugin.audio.musicip/?action=mix_assist_statistics)",
             help="What AI Mix Assist costs and does: requests to the AI, tokens, the rating cache's hit rate, what "
                  "it changed in mixes and stations, and how often you undid it. Today, the last 7 and 30 days, all "
                  "time."),
        dict(id="mix_assist_statistics_reset", type="action", label="Reset statistics",
             data="RunPlugin(plugin://plugin.audio.musicip/?action=mix_assist_statistics_reset)",
             help="Deletes the statistics counted so far (after asking). Statistics are kept for a year."),
    ]),
])
DISCOVERY = ("discovery", 30500, "Discovery mode", [
    (None, [
        dict(id="discovery_excerpt_seconds", type="slider", default="20", range=(5, 1, 60),
             label="Excerpt length (seconds)",
             help="How many seconds of each song Discovery mode and Radio's \"Scan stations\" play."),
        dict(id="discovery_offset_percent", type="slider", default="33", range=(0, 1, 90),
             label="Start offset into song (%)",
             help="Where in each song the excerpt starts, as a share of its length. 33 % skips most intros."),
    ]),
])
RADIO = ("radio", 30600, "Radio", [
    ("AI Mix Assist", [
        dict(id="mix_assist_auto_radio", type="bool", default="true", label="Keep Radio on track",
             help="Takes the songs that clearly don't fit out of a new station's first songs, and checks every "
                  "refill before it is queued. Runs in the background; the radio keeps playing."),
        dict(id="mix_assist_radio_drift", type="enum", default="1", label="Station drift",
             options=["Stay close to the picked song", "Drift slowly", "Wander freely"],
             help="How far a station may wander from the song you picked. Stay close: every song is measured against "
                  "the picked song. Drift slowly: the station has moved half the way to where it went after about 60 "
                  "songs (about 4 hours). Wander freely: after about 20 songs (about 1 hour 20 minutes)."),
        dict(id="mix_assist_station_strictness", type="enum", default="2", label="Station openness", options=OPENNESS,
             help="How much each new song on the radio may surprise you. Focused keeps every song close to the one "
                  "before; Adventurous welcomes bold steps, including songs the AI calls borderline. Same scale as Mix "
                  "openness, set separately."),
        dict(id="mix_assist_station_perspective", type="enum", default="0", label="Station perspective",
             options=PERSPECTIVES,
             help="From which point of view AI Mix Assist works out what a station is about and chooses its songs. "
                  + PERSPECTIVE_HELP + " A favourite station can have its own."),
    ]),
])
LOGGING = ("logging", 30700, "Logging", [
    (None, [
        dict(id="log_general", type="bool", default="false", label="General",
             help="Detailed messages in Kodi's log (kodi.log) about menus and screens, keymaps, track details and "
                  "artwork, MusicIP library reloads and the service's start. Errors and warnings are always logged, "
                  "whatever these switches say."),
        dict(id="log_mixing", type="bool", default="false", label="Mixing",
             help="Every request to MusicIP (seed, parameters, address) with the songs it returned and how long it "
                  "took, and every mix created, opened, refreshed or changed."),
        dict(id="log_ai", type="bool", default="false", label="AI Mix Assist",
             help="Every request to the AI with its full text and its answer, the ratings it gave, both checks for "
                  "every track (distance from the seed, the AI's verdict and reason) and why each replacement was "
                  "taken or passed over. Writes a lot."),
        dict(id="log_radio", type="bool", default="false", label="Radio",
             help="Every step of a running station: what plays and what is queued, each refill with its seed and "
                  "songs, the AI checks and what they changed, and why the station stopped."),
        dict(id="log_discovery", type="bool", default="false", label="Discovery mode",
             help="Every step of Discovery mode: the snippet buffer, skips, playlist positions and player events."),
        dict(id="log_checks", type="bool", default="false", label="Saved-mix checks",
             help="The background check of saved mixes: missing files, the library's state, repair candidates with "
                  "their scores, and every repair made."),
    ]),
])

CATEGORIES = [GENERAL, MIX] + ([AI, RADIO] if WITH_AI else []) + [DISCOVERY, LOGGING]

strings = []  # (id, text)


def string_id(number: int, text: str) -> int:
    strings.append((number, text))
    return number


xml = ['<?xml version="1.0" encoding="utf-8" standalone="yes"?>', '<settings version="1">',
       '    <section id="plugin.audio.musicip">']
for category_id, base, label, groups in CATEGORIES:
    number = base
    xml.append(f'        <category id="{category_id}" label="{string_id(number, label)}">')
    for group_number, (group_label, settings) in enumerate(groups, start=1):
        if group_label:
            number += 1
            xml.append(f'            <group id="{group_number}" label="{string_id(number, group_label)}">')
        else:
            xml.append(f'            <group id="{group_number}">')
        for setting in settings:
            number += 1
            label_id = string_id(number, setting["label"])
            number += 1
            help_id = string_id(number, setting["help"])
            kind = setting["type"]
            xml_type = {"bool": "boolean", "number": "integer", "slider": "integer", "enum": "integer",
                        "text": "string", "action": "action"}[kind]
            xml.append(f'                <setting id="{setting["id"]}" type="{xml_type}" label="{label_id}" help="{help_id}">')
            xml.append('                    <level>0</level>')
            if kind == "action":  # a button: runs its data, the settings dialog closes first
                xml.append(f'                    <data>{escape(setting["data"])}</data>')
                xml.append('                    <constraints><allowempty>true</allowempty></constraints>')
                xml.append('                    <control type="button" format="action"><close>true</close></control>')
                xml.append('                </setting>')
                continue
            xml.append(f'                    <default>{escape(setting["default"])}</default>' if setting["default"] != ""
                       else '                    <default/>')
            if kind == "bool":
                xml.append('                    <control type="toggle"/>')
            elif kind == "number":
                xml.append(f'                    <control type="edit" format="integer"><heading>{label_id}</heading></control>')
            elif kind == "text":
                xml.append('                    <constraints><allowempty>true</allowempty></constraints>')
                xml.append(f'                    <control type="edit" format="string"><heading>{label_id}</heading></control>')
            elif kind == "slider":
                low, step, high = setting["range"]
                xml.append(f'                    <constraints><minimum>{low}</minimum><step>{step}</step>'
                           f'<maximum>{high}</maximum></constraints>')
                xml.append(f'                    <control type="slider" format="integer"><popup>false</popup></control>')
            elif kind == "enum":
                xml.append('                    <constraints>')
                xml.append('                        <options>')
                for value, option in enumerate(setting["options"]):
                    number += 1
                    xml.append(f'                            <option label="{string_id(number, option)}">{value}</option>')
                xml.append('                        </options>')
                xml.append('                    </constraints>')
                xml.append('                    <control type="spinner" format="string"/>')
            xml.append('                </setting>')
        xml.append('            </group>')
    assert number < base + 100, category_id
    xml.append('        </category>')
xml += ['    </section>', '</settings>', '']
(root / "resources" / "settings.xml").write_text("\n".join(xml), encoding="utf-8")


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


po = ['# Kodi Media Center language file', '# Addon Name: MusicIP', '# Addon id: plugin.audio.musicip',
      '# Addon Provider: paradigm_city', 'msgid ""', 'msgstr ""',
      '"Content-Type: text/plain; charset=UTF-8\\n"', '"Content-Transfer-Encoding: 8bit\\n"', '"Language: en_GB\\n"', '']
seen = set()
for number, text in strings:
    assert number not in seen, number
    seen.add(number)
    po += [f'msgctxt "#{number}"', f'msgid {po_quote(text)}', 'msgstr ""', '']
language = root / "resources" / "language" / "resource.language.en_gb"
language.mkdir(parents=True, exist_ok=True)
(language / "strings.po").write_text("\n".join(po), encoding="utf-8")
print(f"{sum(len(group[1]) for c in CATEGORIES for group in c[3])} settings, {len(strings)} strings")
