from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from app.update import APP_VERSION, check_for_update, is_newer, version_parts


class VersionCompareTests(unittest.TestCase):
    def test_a_higher_patch_is_newer(self):
        self.assertTrue(is_newer("0.2.1", "0.2.0"))

    def test_ten_beats_nine(self):
        """String comparison gets this backwards, which is why we parse ints."""
        self.assertTrue(is_newer("0.10.0", "0.9.0"))
        self.assertFalse(is_newer("0.9.0", "0.10.0"))

    def test_the_same_version_is_not_newer(self):
        self.assertFalse(is_newer("0.2.0", "0.2.0"))

    def test_an_older_version_is_not_newer(self):
        self.assertFalse(is_newer("0.1.0", "0.2.0"))

    def test_shorter_and_longer_tags_compare_by_padding(self):
        self.assertFalse(is_newer("0.2", "0.2.0"))
        self.assertTrue(is_newer("0.2.1", "0.2"))

    def test_the_v_prefix_is_optional(self):
        self.assertEqual(version_parts("v0.2.0"), version_parts("0.2.0"))

    def test_a_prerelease_suffix_is_ignored(self):
        self.assertEqual(version_parts("v0.2.0-rc1"), (0, 2, 0))

    def test_a_non_version_tag_is_rejected(self):
        for tag in ("nightly", "", "v", "1.x"):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    version_parts(tag)


class CheckForUpdateTests(unittest.TestCase):
    """The check runs at startup, so no failure of it may reach the user."""

    def _with_tag(self, tag: str, current: str) -> str | None:
        response = types.SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"tag_name": tag}
        )
        fake = types.SimpleNamespace(get=lambda *_a, **_k: response)
        with mock.patch.dict(sys.modules, {"requests": fake}):
            return check_for_update(current)

    def test_a_newer_tag_is_returned_verbatim(self):
        self.assertEqual(self._with_tag("v0.3.0", "0.2.0"), "v0.3.0")

    def test_the_current_tag_reports_no_update(self):
        self.assertIsNone(self._with_tag("v0.2.0", "0.2.0"))

    def test_a_junk_tag_is_no_update_rather_than_a_crash(self):
        self.assertIsNone(self._with_tag("nightly", "0.2.0"))

    def test_a_network_failure_is_no_update_rather_than_a_crash(self):
        def explode(*_a, **_k):
            raise OSError("no network")

        with mock.patch.dict(sys.modules, {"requests": types.SimpleNamespace(get=explode)}):
            self.assertIsNone(check_for_update("0.2.0"))

    def test_the_shipped_version_is_a_parsable_tag(self):
        self.assertGreaterEqual(len(version_parts(APP_VERSION)), 2)


if __name__ == "__main__":
    unittest.main()
