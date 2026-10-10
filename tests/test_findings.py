"""Keeps docs/findings.md in step with the known-issue tests (those marked @unittest.expectedFailure)."""

import os
import re
import unittest

from fake_kodi import ADDON_DIR

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FINDINGS_PATH = os.path.join(ADDON_DIR, "docs", "findings.md")


def iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def collect_tests():
    """All test ids, and the ids of tests marked as known failures."""
    suite = unittest.defaultTestLoader.discover(TESTS_DIR, top_level_dir=TESTS_DIR)
    all_ids, known_failures = set(), set()
    for test in iter_tests(suite):
        all_ids.add(test.id())
        method = getattr(test, getattr(test, "_testMethodName", ""), None)
        if getattr(method, "__unittest_expecting_failure__", False):
            known_failures.add(test.id())
    return all_ids, known_failures


class FindingsDocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FINDINGS_PATH, encoding="utf-8") as handle:
            cls.text = handle.read()
        open_part, _sep, resolved_part = cls.text.partition("\n## Resolved")
        cls.open_section = open_part.partition("\n## Open")[2]
        cls.resolved_section = resolved_part
        cls.all_ids, cls.known_failures = collect_tests()

    def listed_tests(self, section):
        return set(re.findall(r"\*\*Test:\*\*\s*`([\w.]+)`", section))

    def test_sections_exist(self):
        self.assertTrue(self.open_section.strip(), "findings.md needs an '## Open' section")
        self.assertIn("\n## Resolved", self.text)

    def test_every_known_failure_is_listed_as_open(self):
        missing = self.known_failures - self.listed_tests(self.open_section)
        self.assertEqual(missing, set(), "Add these expectedFailure tests to an open finding in docs/findings.md")

    def test_every_listed_test_still_reproduces_its_finding(self):
        listed = self.listed_tests(self.open_section)
        unknown = listed - self.all_ids
        self.assertEqual(unknown, set(), "docs/findings.md lists tests that do not exist")
        fixed = listed - self.known_failures
        self.assertEqual(fixed, set(), "These findings look fixed: move them to '## Resolved' in docs/findings.md")

    def test_finding_numbers_are_unique(self):
        numbers = re.findall(r"^### (F\d+) ", self.text, flags=re.MULTILINE)
        self.assertTrue(numbers)
        self.assertEqual(len(numbers), len(set(numbers)), f"Duplicate finding numbers: {numbers}")


if __name__ == "__main__":
    unittest.main()
