"""The skill folder stays a thin adapter over the one protocol and the one helper."""

from __future__ import annotations

import unittest

from support import ROOT


class Skill(unittest.TestCase):
    def test_skill_has_name_and_description(self):
        text = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")

        header = text.split("---")[1]

        self.assertIn("name: duo", header)
        self.assertIn("description: ", header)

    def test_skill_links_to_the_shared_prompt_and_helper(self):
        for name in ("START_PROMPT.md", "duo.py"):
            with self.subTest(name=name):
                link = ROOT / "skill" / name

                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), (ROOT / name).resolve())


if __name__ == "__main__":
    unittest.main()
