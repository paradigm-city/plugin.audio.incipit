"""AI Mix Assist's statistics: what is counted (AI requests, the rating cache, tidy-ups, radio checks) and the report."""

import json
import os
import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, main, service

from mixassist import claude, rating, usage
from mixassist.cache import RatingCache
from mixassist.dimensions import build_system_prompt

CLI_ANSWER = {"type": "result", "subtype": "success", "is_error": False, "structured_output": {"tracks": []},
              "total_cost_usd": 0.0421, "usage": {"input_tokens": 1200, "output_tokens": 300,
                                                  "cache_read_input_tokens": 9000, "cache_creation_input_tokens": 500}}


class Completed:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, "", returncode


class UsageTestCase(KodiTestCase):
    def events(self, kind=None):
        return [event for event in main.usage_log().events() if kind is None or event[1] == kind]


class CountingTest(UsageTestCase):
    def test_an_ai_request_is_counted_with_its_purpose_tokens_and_cost(self):
        runner = mock.Mock(return_value=Completed(json.dumps(CLI_ANSWER)))
        claude.ask("claude", main.mix_assist_checks.INTENT_PROMPT + "\n\nmore", {}, "message", runner=runner)
        (_ts, _kind, fields), = self.events("ai_call")
        self.assertEqual((fields["purpose"], fields["ok"], fields["input_tokens"], fields["cache_read_tokens"],
                          fields["cost_usd"]), ("judging", True, 1200, 9000, 0.0421))
        self.assertNotIn("system_prompt", fields)  # only the purpose is kept

    def test_a_failed_request_is_counted_with_its_kind(self):
        answer = dict(CLI_ANSWER, is_error=True, subtype="error", result="You've hit your usage limit")
        with self.assertRaises(claude.ClaudeError):
            claude.ask("claude", build_system_prompt(), {}, "m", runner=mock.Mock(return_value=Completed(json.dumps(answer))))
        (_ts, _kind, fields), = self.events("ai_call")
        self.assertEqual((fields["purpose"], fields["ok"], fields["failure"]), ("rating", False, claude.USAGE_LIMIT))

    def test_the_rating_cache_counts_hits_misses_and_new_ratings(self):
        store = RatingCache(os.path.join(kodi.root, "ratings.db"))
        store.put("rg:a", {key: 5 for key in rating.ALL_KEYS} | {"sounding_year": 1990}, model="m", source="t")
        units = [{"key": key, "kind": "album", "item": {"title": key}} for key in ("rg:a", "rg:b", "rg:c")]
        with mock.patch.object(rating, "parse_ratings", return_value={}):
            rating.rate_missing(units, store, ask=lambda *args: {})
        store.close()
        self.assertEqual([fields for _ts, _kind, fields in self.events("cache")], [{"hits": 1, "misses": 2}])
        self.assertEqual([fields["count"] for _ts, _kind, fields in self.events("rated")], [0])

    def test_mix_events_come_with_the_mix_history(self):
        cache_path = self.save_mix(["D:\\a.mp3", "D:\\b.mp3"], seed="D:\\a.mp3")
        main.record_mix_history(cache_path, "ai_tidy_up", automatic=True, judged=40, replaced=[{}, {}], removed=[{}])
        main.record_mix_history(cache_path, "ai_undone", tracks=40)
        main.record_mix_history(cache_path, "created", tracks=40)  # not an AI Mix Assist event
        total = usage.summarise(self.events())
        self.assertEqual((total["tidy_ups_automatic"], total["judged"], total["replaced"], total["removed"],
                          total["tidy_ups_changed"], total["undone"]), (1, 40, 2, 1, 1, 1))
        self.assertEqual(len(self.events("mix")), 2)

    def test_radio_events_are_counted(self):
        state = {}
        service.add_radio_event(state, "refill", checked=True, added=["x"] * 6, skipped_count=20)
        service.add_radio_event(state, "refill_unchecked", reason="the AI check took too long", added=["x"] * 6)
        total = usage.summarise(self.events("radio"))
        self.assertEqual((total["radio_refills"], total["radio_kept"], total["radio_skipped"],
                          total["radio_unchecked_slow"]), (1, 6, 20, 1))

    def test_old_events_are_pruned(self):
        log = main.usage_log()
        log.record("cache", ts=int(time.time()) - 400 * 86400, hits=1, misses=0)
        log.record("cache", hits=2, misses=0)
        self.assertEqual(log.prune(), 1)
        self.assertEqual(len(log.events()), 1)


class SummaryTest(unittest.TestCase):
    def test_days_are_local_days_today_last(self):
        now = time.mktime((2026, 10, 19, 12, 0, 0, 0, 0, -1))
        events = [(int(now) - 86400, "ai_call", {"purpose": "rating", "ok": True}),
                  (int(now), "ai_call", {"purpose": "judging", "ok": True}),
                  (int(now) - 40 * 86400, "ai_call", {"purpose": "rating", "ok": True})]  # outside the days
        days = usage.daily(events, 3, now, ["requests_rating", "requests_judging"])
        self.assertEqual(days, [{"requests_rating": 0, "requests_judging": 0}, {"requests_rating": 1, "requests_judging": 0},
                                {"requests_rating": 0, "requests_judging": 1}])

    def test_round_axis_ends(self):
        from support import main as plugin
        self.assertEqual([plugin.nice_ceiling(value) for value in (3, 10, 11, 21, 51, 199, 510)], [10, 10, 20, 50, 100, 200, 1000])

    def test_without_a_sink_nothing_happens(self):
        sink = usage._SINK
        try:
            usage.set_sink(None)
            usage.emit("cache", hits=1)
            usage.set_sink(lambda *args, **kwargs: 1 / 0)
            usage.emit("cache", hits=1)  # a failing sink never fails the work
        finally:
            usage.set_sink(sink)


class ReportTest(UsageTestCase):
    def record(self):
        log = main.usage_log()
        log.record("ai_call", purpose="rating", ok=True, input_tokens=1000, output_tokens=200, cache_read_tokens=9000,
                   cache_write_tokens=0, cost_usd=0.5, seconds=6.0)
        log.record("ai_call", purpose="judging", ok=False, failure=claude.USAGE_LIMIT, seconds=1.0)
        log.record("cache", hits=90, misses=10)
        log.record("rated", count=10)
        log.record("mix", event="ai_tidy_up", automatic=False, judged=40, replaced=3, removed=0)
        log.record("mix", event="ai_undone")
        log.record("radio", event="refill", checked=True, added=6, skipped=14)

    def test_the_report_has_four_tabs(self):
        self.record()
        self.run_plugin(action="mix_assist_statistics")
        window = kodi.windows[-1]
        titles = [window.properties.get(f"tab{number}") for number in range(1, 6)]
        self.assertEqual(titles, ["AI requests", "Rating cache", "Mix Assist", "Radio", None])
        self.assertTrue(window.properties["facts"].startswith("Counted since 20"))
        self.assertIn("| 2 AI requests", window.properties["facts"])
        text = window.properties["text"]
        self.assertIn("[B]Today[/B]\n2 requests: 1 rating, 1 judging\n1 failed (usage limit 1)", text)
        self.assertIn("Tokens: 10 k in (9 k of them from Claude's prompt cache), 200 out", text)
        self.assertIn("Equivalent API cost: $0.50", text)
        self.assertTrue(os.path.isfile(window.properties["image"]))
        window.onFocus(202)
        self.assertIn("Albums looked up: 100, already rated: 90 (90 %)\nNewly rated: 10", window.properties["text"])
        window.onFocus(203)
        self.assertIn("Undone by you: 1 of 1 tidy-ups that changed a mix (100 %)", window.properties["text"])
        window.onFocus(204)
        self.assertIn("Refills checked: 1; songs kept 6, skipped 14 (30 % kept)", window.properties["text"])

    def test_nothing_counted_yet(self):
        self.run_plugin(action="mix_assist_statistics")
        self.assertIn("Nothing counted yet", kodi.dialogs("ok")[0][1][1])

    def test_reset_asks_first(self):
        self.record()
        kodi.respond("yesno", False)
        self.run_plugin(action="mix_assist_statistics_reset")
        self.assertTrue(main.usage_log().events())
        kodi.respond("yesno", True)
        self.run_plugin(action="mix_assist_statistics_reset")
        self.assertEqual(main.usage_log().events(), [])


if __name__ == "__main__":
    unittest.main()
