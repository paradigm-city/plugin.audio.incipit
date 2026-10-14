"""AI Mix Assist in the add-on: tidying up saved mixes from the context menu, undo, editing the intent."""

import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, MusicIPServerTestCase, main, service

TRACKS = [
    "D:\\music\\#jazz\\Seed.mp3",
    "D:\\music\\#jazz\\Fits.mp3",
    "D:\\music\\#disco\\Fire Walk.mp3",
    "D:\\music\\#jazz\\Fits Too.mp3",
    "D:\\music\\#pop\\Who Do You Love.mp3",
]
REPLACEMENT = "D:\\music\\#jazz\\Replacement.mp3"
ORIGINAL_ASK = main.mix_assist_ask


def row(position, label, status="fits"):
    return {"position": position, "unit": {"label": label}, "status": status}


def plan(changes=(), removed=(), intent="dark, abstract, instrumental", source="ai"):
    paths = list(TRACKS)
    for change in changes:
        paths[change["position"] - 1] = change["new"]
    paths = [path for index, path in enumerate(paths, start=1) if index not in removed]
    return {"intent": intent, "intent_source": source, "changes": list(changes), "removed": list(removed),
            "paths": paths, "rebuild_suggested": False,
            "rows": [row(i, f"Track {i}", "outlier" if i in (3, 5) else "fits") for i in range(1, 6)]}


REPLACE_DISCO = {"position": 3, "old": TRACKS[2], "old_label": "wilfried – fire walk", "new": REPLACEMENT,
                 "new_label": "Medeski Martin & Wood – Think", "reason": "Danceable disco, bright", "source": "submix"}


class MixAssistTestCase(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix(TRACKS)
        patcher = mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tidy_up(self, result, **kwargs):
        with mock.patch.object(main.mix_assist, "tidy_up", return_value=result) as tidy_up:
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path, **kwargs)
        return tidy_up

    def section(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path)).get("mix_assist", {})


class TidyUpTest(MixAssistTestCase):
    def test_replacements_are_applied_recorded_and_announced(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])
        section = self.section()
        self.assertEqual(section["intent"], "dark, abstract, instrumental")
        self.assertEqual(section["intent_source"], "ai")
        self.assertEqual(section["previous_tracks"], TRACKS)
        self.assertEqual(section["replaced"][0]["new_label"], "Medeski Martin & Wood – Think")
        self.assertEqual(section["removed"], ["Track 5"])
        self.assertNotified("AI Mix Assist: 1 track didn't fit and was replaced, 1 without a fitting replacement was removed.")
        self.assertBuiltin("Container.Refresh")

    def test_a_fitting_mix_is_left_unchanged(self):
        self.tidy_up(plan())
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("AI Mix Assist: every track fits.")

    def test_settings_and_the_listeners_intent_are_passed_on(self):
        kodi.settings.update({"mix_assist_strictness": "4", "mix_reject_size": "3"})
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"listener_intent": "my own words"}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        tidy_up = self.tidy_up(plan(intent="my own words", source="listener"))
        args, kwargs = tidy_up.call_args
        self.assertEqual(args[0], TRACKS)
        self.assertEqual(kwargs["intent"], "my own words")
        self.assertEqual(kwargs["strictness"], 1.0)
        self.assertEqual(kwargs["artist_window"], 3)
        self.assertEqual(self.section()["listener_intent"], "my own words")

    def test_progress_is_shown_in_the_background_and_closed(self):
        def tidy_up(*args, **kwargs):
            kwargs["progress"]("Rating new music")
            return plan()

        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=tidy_up):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        calls = [call[0] for call in kodi.dialog_calls if call[0].startswith("progress")]
        self.assertEqual(calls[0], "progress.create")
        self.assertIn("progress.update", calls)
        self.assertEqual(calls[-1], "progress.close")

    def test_claude_problems_become_plain_messages(self):
        error = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=error):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        self.assertNotified("Claude's usage limit is reached")
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)

    def test_a_missing_cli_is_reported(self):
        with mock.patch.object(main, "mix_assist_ask", ORIGINAL_ASK), \
                mock.patch.object(main.mix_assist_claude, "find_cli", return_value=""):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        self.assertNotified("AI Mix Assist needs the Claude Code CLI")


class UndoTest(MixAssistTestCase):
    def test_undo_restores_the_previous_tracks(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertNotIn("replaced", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("AI Mix Assist: the changes were undone.")

    def test_nothing_to_undo(self):
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertNotified("There are no AI Mix Assist changes to undo.")


class EditIntentTest(MixAssistTestCase):
    def test_the_listener_can_write_and_clear_the_intent(self):
        self.tidy_up(plan())
        kodi.respond("input", "complex, abstract, not danceable")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertEqual(kodi.dialogs("input")[-1][1], ("What is this mix about?", "dark, abstract, instrumental"))
        self.assertEqual(self.section()["listener_intent"], "complex, abstract, not danceable")
        self.assertNotified("Saved. Tidy up the mix to apply it.")

        kodi.respond("input", "  ")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())

    def test_cancelling_keeps_the_intent(self):
        self.tidy_up(plan())
        kodi.respond("input", "dark, abstract, instrumental")  # unchanged text, as when cancelled with the default
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())


class SavedMixMenuTest(MixAssistTestCase):
    def context_labels(self):
        kodi.directory_items.clear()
        main.add_saved_mix_item(self.cache_path)
        return [label for label, _action in kodi.directory_items[-1][1].context_menu]

    def test_entries_and_undo_only_after_a_change(self):
        labels = self.context_labels()
        self.assertIn("Tidy up with AI Mix Assist", labels)
        self.assertIn("Edit what this mix is about", labels)
        self.assertNotIn("Undo AI Mix Assist changes", labels)
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.assertIn("Undo AI Mix Assist changes", self.context_labels())

    def test_mix_information_shows_the_intent_and_the_changes(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        message = main.build_mix_info_message(self.cache_path)
        self.assertIn("What this mix is about (stated by the AI): dark, abstract, instrumental", message)
        self.assertIn("Replaced: wilfried – fire walk → Medeski Martin & Wood – Think (Danceable disco, bright)", message)


class SubmixFetcherTest(MusicIPServerTestCase):
    def test_musicip_reloads_only_before_the_first_submix(self):
        self.musicip.set_mix(TRACKS[1], [TRACKS[3]])
        self.musicip.set_mix(TRACKS[0], [TRACKS[1], TRACKS[3]])
        fetch = main.mix_assist_fetcher()
        self.assertEqual(fetch(TRACKS[1], 15), [TRACKS[1], TRACKS[3]])
        self.assertEqual(fetch(TRACKS[0], 45), [TRACKS[0], TRACKS[1], TRACKS[3]])
        self.assertEqual(self.musicip.reload_count(), 1)
        self.assertEqual([query["size"] for query in self.musicip.mix_requests()], ["15", "45"])

    def test_each_tidy_up_reloads_once(self):
        self.musicip.set_mix(TRACKS[0], [TRACKS[1]])
        main.mix_assist_fetcher()(TRACKS[0], 15)
        main.mix_assist_fetcher()(TRACKS[0], 15)
        self.assertEqual(self.musicip.reload_count(), 2)


class NewMixQueueTest(KodiTestCase):
    def queued(self):
        return self.read_json(main.mix_assist_queue_path()).get("entries", [])

    def test_new_mixes_are_queued_once_in_the_chosen_mode(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS[:3])
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS[:4])  # regenerated: replaces the older request
        self.assertEqual([(e["cache_path"], e["mode"], len(e["tracks"])) for e in self.queued()],
                         [("b.m3u", "fix", 3), ("a.m3u", "fix", 4)])
        kodi.settings["mix_assist_new_mixes"] = "1"
        main.queue_mix_assist_for_new_mix("c.m3u", TRACKS)
        self.assertEqual(self.queued()[-1]["mode"], "show")

    def test_nothing_is_queued_when_switched_off_or_too_short(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS[:1])
        kodi.settings["mix_assist_new_mixes"] = "0"
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS)
        self.assertEqual(self.queued(), [])

    def test_requests_are_taken_oldest_first(self):
        self.assertEqual(main.pop_mix_assist_request(), {})
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS)
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "a.m3u")
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "b.m3u")
        self.assertEqual(main.pop_mix_assist_request(), {})


class NewMixGenerationQueueTest(MusicIPServerTestCase):
    def test_a_generated_mix_is_queued(self):
        self.musicip.set_mix(TRACKS[0], TRACKS[1:])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        entries = self.read_json(main.mix_assist_queue_path()).get("entries", [])
        self.assertEqual([(e["cache_path"], e["tracks"]) for e in entries],
                         [(main.mix_cache_path(TRACKS[0], 20), TRACKS)])


class ProcessNewMixTest(MixAssistTestCase):
    def request(self, mode="fix"):
        return {"cache_path": self.cache_path, "tracks": list(TRACKS), "mode": mode}

    def process(self, result, mode="fix"):
        with mock.patch.object(main.mix_assist, "tidy_up", return_value=result) as tidy_up:
            main.process_mix_assist_request(self.request(mode))
        return tidy_up

    def play_mix(self, position):
        playlist = main.get_music_playlist()
        for track in TRACKS:
            playlist.add(track)
        kodi.go_to(position)

    def test_fix_saves_the_replacements_and_notifies(self):
        tidy_up = self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertTrue(tidy_up.call_args[1]["find_replacements"])
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])
        self.assertEqual(self.section()["previous_tracks"], TRACKS)
        self.assertNotified("1 track didn't fit and was replaced")

    def test_show_only_records_the_tracks_that_dont_fit(self):
        result = plan()
        result["outliers"] = [3]
        result["rows"][2]["reason"] = "Danceable disco, bright"
        tidy_up = self.process(result, mode="show")
        self.assertFalse(tidy_up.call_args[1]["find_replacements"])
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertEqual(self.section()["not_fitting"], [{"label": "Track 3", "reason": "Danceable disco, bright"}])
        self.assertNotIn("previous_tracks", self.section())
        self.assertNotified("AI Mix Assist: 1 track may not fit.")
        self.assertIn("Doesn't fit: Track 3 (Danceable disco, bright)", main.build_mix_info_message(self.cache_path))

    def test_a_mix_changed_since_it_was_queued_is_skipped(self):
        main.save_mix_by_cache_path(self.cache_path, TRACKS[:3])
        tidy_up = self.process(plan(changes=[REPLACE_DISCO]))
        tidy_up.assert_not_called()
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:3])

    def test_a_mix_changed_during_the_check_is_left_alone(self):
        def tidy_up(*args, **kwargs):
            main.save_mix_by_cache_path(self.cache_path, TRACKS[:3])
            return plan(changes=[REPLACE_DISCO])

        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=tidy_up):
            main.process_mix_assist_request(self.request())
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:3])

    def test_claude_problems_are_reported_without_changes(self):
        error = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=error):
            main.process_mix_assist_request(self.request())
        self.assertNotified("Claude's usage limit is reached")
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)

    def test_the_playing_mix_is_patched_after_the_next_track(self):
        self.play_mix(0)
        self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(kodi.playlist_files(), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])

    def test_the_playing_track_and_the_next_one_are_never_touched(self):
        self.play_mix(1)  # track 3 (the disco one) is next
        self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(kodi.playlist_files(), TRACKS[:4])
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])

    def test_another_playlist_is_not_patched(self):
        main.get_music_playlist().add(TRACKS[0])
        main.get_music_playlist().add(TRACKS[2])
        kodi.go_to(0)
        self.process(plan(changes=[REPLACE_DISCO]))
        self.assertEqual(kodi.playlist_files(), [TRACKS[0], TRACKS[2]])


class ServiceTickTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        service.MIX_ASSIST_WORKER = None
        self.addCleanup(setattr, service, "MIX_ASSIST_WORKER", None)
        patcher = mock.patch.object(service, "load_plugin_module", return_value=main)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_queued_mix_is_processed_in_a_background_thread(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        with mock.patch.object(main, "process_mix_assist_request") as process:
            service.run_mix_assist_tick()
            service.MIX_ASSIST_WORKER.join(5)
        self.assertEqual(process.call_args[0][0]["cache_path"], "a.m3u")
        self.assertEqual(main.pop_mix_assist_request(), {})

    def test_one_mix_at_a_time(self):
        busy = mock.Mock(is_alive=mock.Mock(return_value=True))
        service.MIX_ASSIST_WORKER = busy
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        service.run_mix_assist_tick()
        self.assertIs(service.MIX_ASSIST_WORKER, busy)
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "a.m3u")

    def test_failures_in_the_worker_are_logged(self):
        with mock.patch.object(main, "process_mix_assist_request", side_effect=RuntimeError("boom")):
            service.run_mix_assist_request(main, {"cache_path": "a.m3u"})  # must not raise


class StrictnessSettingTest(KodiTestCase):
    def test_steps_map_to_thresholds(self):
        self.assertEqual(main.get_mix_assist_strictness(), 1.2)
        for value, expected in (("0", 1.5), ("4", 1.0), ("9", 1.0), ("x", 1.2)):
            kodi.settings["mix_assist_strictness"] = value
            self.assertEqual(main.get_mix_assist_strictness(), expected)


if __name__ == "__main__":
    unittest.main()
