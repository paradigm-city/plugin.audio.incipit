"""AI Mix Assist core: dimensions and prompt, the Claude CLI route, the rating cache."""

import ast
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

from fake_kodi import ADDON_DIR

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

from mixassist import cache, claude, dimensions  # noqa: E402

# The rating prompt's fingerprint. Changing the prompt makes every cached rating invalid (they are re-rated when
# next needed), so a change must be deliberate: update this value together with the prompt.
EXPECTED_PROMPT_VERSION = "b42cee6d875f"


def rating(**values):
    base = {key: 5 for key in dimensions.SCALE_KEYS}
    base.update({dimensions.ERA_KEY: 1990, "familiarity": 1, "character": "x"})
    base.update(values)
    return base


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class FakeRunner:
    """Records the calls a module makes to subprocess.run and answers them in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class PackageTest(unittest.TestCase):
    def test_package_is_python_3_8_and_kodi_free(self):
        for path in glob.glob(os.path.join(ADDON_DIR, "mixassist", "*.py")):
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            ast.parse(source, filename=path, feature_version=(3, 8))
            self.assertNotRegex(source, r"(?m)^\s*import xbmc|^\s*from xbmc", path)


class DimensionsTest(unittest.TestCase):
    def test_version_2_dimensions(self):
        self.assertEqual(dimensions.ALL_KEYS, ("energy", "exploration", "mood", "making", "danceability",
                                               "production", "form", "sounding_year"))

    def test_prompt_version_is_unchanged(self):
        self.assertEqual(cache.prompt_version(), EXPECTED_PROMPT_VERSION)


class CliDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def touch(self, *parts):
        path = os.path.join(self.home, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def extension(self, version):
        return self.touch(".vscode", "extensions", f"anthropic.claude-code-{version}-win32-x64", "resources",
                          "native-binary", "claude.exe")

    def test_newest_extension_first(self):
        old, new = self.extension("2.1.296"), self.extension("2.1.299")
        self.assertEqual(claude.cli_candidates(home=self.home, appdata=self.home, which=lambda name: None), [new, old])

    def test_standalone_install_is_preferred(self):
        extension = self.extension("2.1.299")
        standalone = self.touch(".local", "bin", "claude.exe")
        candidates = claude.cli_candidates(home=self.home, appdata=self.home, which=lambda name: None)
        self.assertEqual(candidates, [standalone, extension])

    def test_configured_path_wins_if_it_exists(self):
        extension = self.extension("2.1.299")
        configured = self.touch("tools", "claude.exe")
        kwargs = {"home": self.home, "appdata": self.home, "which": lambda name: None}
        self.assertEqual(claude.find_cli(configured, **kwargs), configured)
        self.assertEqual(claude.find_cli(os.path.join(self.home, "missing.exe"), **kwargs), extension)
        self.assertEqual(claude.find_cli("", home=tempfile.mkdtemp(), appdata=self.home, which=lambda name: None), "")


class CliCallTest(unittest.TestCase):
    def success(self, structured):
        return FakeCompleted(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                         "result": "", "structured_output": structured}))

    def test_api_credentials_are_never_passed_on(self):
        environment = claude.cli_environment({"ANTHROPIC_API_KEY": "sk-ant-x", "ANTHROPIC_AUTH_TOKEN": "t", "PATH": "p"})
        self.assertEqual(environment, {"PATH": "p"})

    def test_ask_runs_quietly_without_credentials_and_returns_the_structured_output(self):
        runner = FakeRunner(self.success({"ratings": []}))
        with unittest.mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-x"}):
            result = claude.ask("claude.exe", "system", {"type": "object"}, "message", runner=runner)
        self.assertEqual(result, {"ratings": []})
        command, kwargs = runner.calls[0]
        self.assertEqual(command[:2], ["claude.exe", "-p"])
        self.assertNotIn("--bare", command)  # --bare only accepts API keys, bypassing the subscription
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--system-prompt") + 1], "system")
        self.assertEqual(kwargs["input"], "message")
        self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], claude.CREATE_NO_WINDOW)

    def test_failures_are_classified(self):
        cases = [
            (FakeCompleted(json.dumps({"subtype": "success", "is_error": True, "api_error_status": 429,
                                       "result": "rate limited"})), claude.USAGE_LIMIT),
            (FakeCompleted(json.dumps({"subtype": "success", "is_error": True,
                                       "result": "Claude AI usage limit reached|1760000000"})), claude.USAGE_LIMIT),
            (FakeCompleted("", "Not logged in · Please run /login"), claude.NOT_LOGGED_IN),
            (FakeCompleted(json.dumps({"subtype": "error_during_execution", "is_error": True, "result": "boom"})),
             claude.FAILED),
            (subprocess.TimeoutExpired("claude", 1), claude.TIMEOUT),
            (FileNotFoundError("claude.exe"), claude.NOT_FOUND),
        ]
        for answer, kind in cases:
            with self.subTest(kind=kind):
                with self.assertRaises(claude.ClaudeError) as caught:
                    claude.ask("claude.exe", "s", {}, "m", runner=FakeRunner(answer))
                self.assertEqual(caught.exception.kind, kind)

    def test_missing_cli(self):
        with self.assertRaises(claude.ClaudeError) as caught:
            claude.ask("", "s", {}, "m")
        self.assertEqual(caught.exception.kind, claude.NOT_FOUND)

    def test_check_keeps_only_yes_and_no(self):
        status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "someone@example.com"})
        result = claude.check("claude.exe", runner=FakeRunner(FakeCompleted("2.1.299 (Claude Code)\n"),
                                                              FakeCompleted(status)))
        self.assertEqual(result, {"found": True, "version": "2.1.299", "logged_in": True, "subscription": True})
        self.assertNotIn("example.com", json.dumps(result))
        self.assertEqual(claude.check("")["found"], False)


class RatingCacheTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "mixassist", "ratings.db")

    def test_put_and_get(self):
        store = cache.RatingCache(self.path)
        store.put("rg:1", rating(energy=8, familiarity=2), model="m", source="test")
        entry = store.get("rg:1")
        self.assertEqual(entry["energy"], 8)
        self.assertEqual((entry["familiarity"], entry["description"]), (2, "x"))
        self.assertIsNone(store.get("rg:2"))
        store.close()

    def test_entries_of_another_prompt_version_are_ignored(self):
        cache.RatingCache(self.path, version="old").put("rg:1", rating(), model="m", source="test")
        self.assertIsNone(cache.RatingCache(self.path).get("rg:1"))
        self.assertEqual(cache.RatingCache(self.path, version="old").count(), 1)

    def test_library_reference_by_kind(self):
        store = cache.RatingCache(self.path)
        store.put("rg:1", rating(energy=1), model="m", source="test")
        store.put("album:a|b", rating(energy=2), model="m", source="test")
        store.put("rec:1", rating(energy=3), model="m", source="test")
        self.assertEqual(sorted(vector["energy"] for vector in store.library()), [1, 2])
        self.assertEqual([vector["energy"] for vector in store.library("track")], [3])

    def test_import_pilot_takes_current_entries_without_overwriting(self):
        store = cache.RatingCache(self.path)
        store.put("rg:keep", rating(energy=9), model="m", source="test")
        pilot = {"units": {
            "rg:keep": dict(rating(energy=1), prompt_version=store.version),
            "rg:new": dict(rating(energy=4), prompt_version=store.version, model="claude-opus-5-5"),
            "rg:old": dict(rating(), prompt_version="other"),
            "rg:broken": {"prompt_version": store.version, "energy": 3},
        }}
        pilot_path = os.path.join(tempfile.mkdtemp(), "rating_cache.json")
        with open(pilot_path, "w", encoding="utf-8") as handle:
            json.dump(pilot, handle)
        self.assertEqual(store.import_pilot(pilot_path), 1)
        self.assertEqual(store.get("rg:keep")["energy"], 9)
        self.assertEqual(store.get("rg:new")["energy"], 4)
        self.assertIsNone(store.get("rg:old"))

    def test_unit_keys(self):
        self.assertEqual(cache.album_key("ERRA", "Cure", "rg-9"), "rg:rg-9")
        self.assertEqual(cache.album_key("ERRA", "Cure"), cache.album_key("Erra", "CURE"))
        self.assertEqual(cache.track_key("Molvær", "Khmer"), cache.track_key("molvaer", "Khmer!"))
        self.assertEqual(cache.track_key("x", "y", "rec-1"), "rec:rec-1")
        self.assertEqual(cache.kind_of_key("album:x|y"), "album")
        self.assertEqual(cache.kind_of_key("track:x|y"), "track")

    def test_compilations(self):
        self.assertTrue(cache.is_compilation(True, "Band", 1))
        self.assertTrue(cache.is_compilation(False, "Various Artists", 1))
        self.assertTrue(cache.is_compilation(False, "Band", cache.COMPILATION_ARTIST_LIMIT + 1))
        self.assertFalse(cache.is_compilation(False, "Band", 2))


if __name__ == "__main__":
    unittest.main()
