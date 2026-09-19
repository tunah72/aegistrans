"""Tests for medical specialty profiles manager."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdf2zh.profiles import (
    find_project_root,
    get_profiles_base_dir,
    list_available_profiles,
    load_profile,
    resolve_profile_dir,
    validate_profile,
)


class ProfilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = find_project_root()
        self.profiles_dir = get_profiles_base_dir(self.root)

    def test_list_available_profiles(self):
        profiles = list_available_profiles(self.root)
        self.assertIn("dental", profiles)
        self.assertIn("general_medicine", profiles)

    def test_resolve_profile_by_name(self):
        dental_path = resolve_profile_dir("dental", root=self.root)
        self.assertIsNotNone(dental_path)
        self.assertTrue(dental_path.is_dir())
        self.assertEqual(dental_path.name, "dental")

        gm_path = resolve_profile_dir("general_medicine", root=self.root)
        self.assertIsNotNone(gm_path)
        self.assertTrue(gm_path.is_dir())

    def test_resolve_nonexistent_profile(self):
        result = resolve_profile_dir("nonexistent_specialty_xyz", root=self.root)
        self.assertIsNone(result)

    def test_load_profile_dental(self):
        assets = load_profile("dental", root=self.root)
        self.assertIsNotNone(assets)
        self.assertEqual(assets.name, "dental")
        self.assertIsNotNone(assets.system_prompt)
        self.assertTrue(assets.system_prompt.is_file())
        self.assertIsNotNone(assets.glossary)
        self.assertTrue(assets.glossary.is_file())

    def test_load_profile_general_medicine(self):
        assets = load_profile("general_medicine", root=self.root)
        self.assertIsNotNone(assets)
        self.assertEqual(assets.name, "general_medicine")
        self.assertIsNotNone(assets.system_prompt)
        self.assertTrue(assets.system_prompt.is_file())
        self.assertIsNotNone(assets.glossary)
        self.assertTrue(assets.glossary.is_file())

    def test_validate_existing_profiles(self):
        for profile_name in ["dental", "general_medicine"]:
            p_dir = self.profiles_dir / profile_name
            res = validate_profile(p_dir)
            self.assertTrue(
                res["valid"],
                f"Profile '{profile_name}' failed validation: {res.get('error')}",
            )
            self.assertTrue(res["has_prompt"])
            self.assertTrue(res["has_glossary"])
            self.assertGreater(res["glossary_terms"], 50)

    def test_validate_invalid_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Empty directory should fail
            res = validate_profile(tmp_path)
            self.assertFalse(res["valid"])
            self.assertIn("Missing", res["error"])


if __name__ == "__main__":
    unittest.main()
