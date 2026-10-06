"""install.sh: links the skill for both agents, is safe to rerun, and updates a git checkout."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from support import ROOT

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


class Install(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.home)}

    def copy_repo(self, target: Path) -> Path:
        """A minimal copy of the repository: the installer and the skill folder with its links."""
        (target / "skill").mkdir(parents=True)
        shutil.copy2(ROOT / "install.sh", target / "install.sh")
        shutil.copy2(ROOT / "skill" / "SKILL.md", target / "skill" / "SKILL.md")
        return target

    def install(self, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run([str(repo / "install.sh")], env=self.env, capture_output=True, text=True,
                              timeout=60)

    def git(self, repo: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env, capture_output=True,
                              text=True, check=True).stdout.strip()

    def test_links_both_agents_and_is_safe_to_rerun(self):
        repo = self.copy_repo(self.base / "duo")
        (repo / "skill" / "skill").symlink_to(repo / "skill")

        first = self.install(repo)
        second = self.install(repo)

        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
        for link in (self.home / ".claude/skills/duo", self.home / ".agents/skills/duo"):
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), (repo / "skill").resolve())
        self.assertFalse((repo / "skill" / "skill").exists())
        self.assertIn("export PATH=", second.stdout)

    def test_a_real_folder_in_the_way_is_left_alone(self):
        repo = self.copy_repo(self.base / "duo")
        mine = self.home / ".claude/skills/duo"
        mine.mkdir(parents=True)

        done = self.install(repo)

        self.assertEqual(done.returncode, 0)
        self.assertFalse(mine.is_symlink())
        self.assertIn("left alone", done.stderr)
        self.assertTrue((self.home / ".agents/skills/duo").is_symlink())

    def test_a_git_checkout_is_updated(self):
        origin = self.copy_repo(self.base / "origin")
        self.git(origin, "init", "-q")
        self.git(origin, "add", ".")
        self.git(origin, "commit", "-q", "-m", "first")
        clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], env=self.env, check=True)
        (origin / "NEW.md").write_text("new\n", encoding="utf-8")
        self.git(origin, "add", "NEW.md")
        self.git(origin, "commit", "-q", "-m", "second")

        done = self.install(clone)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((clone / "NEW.md").exists())
        self.assertIn("second", done.stdout)


if __name__ == "__main__":
    unittest.main()
