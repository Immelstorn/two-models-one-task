"""install.sh: installs into ~/.local/share/duo, links the skill and launcher, reruns safely, uninstalls."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from support import ROOT


class Install(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DUO_")}
        self.env["HOME"] = str(self.home)
        self.installed = self.home / ".local/share/duo"

    def archive(self) -> str:
        """A local release archive whose installer prints a marker, as a file:// address."""
        top = self.base / "release" / "duo-main"
        top.mkdir(parents=True)
        subprocess.run(f"tar -cf - duo.py START_PROMPT.md skill bin install.sh LICENSE | tar -xf - -C '{top}'",
                       shell=True, cwd=ROOT, check=True)
        installer = top / "install.sh"
        lines = installer.read_text(encoding="utf-8").splitlines(keepends=True)
        installer.write_text(lines[0] + "echo newest-installer-ran\n" + "".join(lines[1:]), encoding="utf-8")
        tarball = self.base / "main.tar.gz"
        subprocess.run(["tar", "-czf", str(tarball), "-C", str(top.parent), "duo-main"], check=True)
        return f"file://{tarball}"

    def install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def test_installs_files_and_links_and_reruns_safely(self):
        first = self.install("--from", str(ROOT))
        second = self.install("--from", str(ROOT))

        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
        self.assertTrue((self.installed / "duo.py").is_file())
        self.assertEqual((self.installed / "skill" / "duo.py").resolve(), (self.installed / "duo.py").resolve())
        for link in (self.home / ".claude/skills/duo", self.home / ".agents/skills/duo"):
            self.assertEqual(link.resolve(), (self.installed / "skill").resolve())
        self.assertEqual((self.home / ".local/bin/duo").resolve(), (self.installed / "bin/duo").resolve())
        self.assertEqual(sorted(p.name for p in self.installed.parent.iterdir()), ["duo"])
        self.assertIn("export PATH=", second.stderr)
        self.assertIn("Already up to date", second.stdout)

    def test_a_real_folder_in_the_way_is_left_alone(self):
        mine = self.home / ".claude/skills/duo"
        mine.mkdir(parents=True)

        done = self.install("--from", str(ROOT))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(mine.is_symlink())
        self.assertIn("left alone", done.stderr)
        self.assertTrue((self.home / ".agents/skills/duo").is_symlink())

    def test_a_broken_source_keeps_the_previous_install(self):
        self.install("--from", str(ROOT))
        broken = self.base / "broken"
        broken.mkdir()
        (broken / "duo.py").write_text("# incomplete\n", encoding="utf-8")

        done = self.install("--from", str(broken))

        self.assertEqual(done.returncode, 1)
        self.assertIn("nothing changed", done.stderr)
        self.assertEqual((self.installed / "duo.py").read_bytes(), (ROOT / "duo.py").read_bytes())

    def test_uninstall_removes_only_what_it_installed(self):
        self.install("--from", str(ROOT))
        other = self.home / ".claude/skills/other"
        other.mkdir()

        done = self.install("--uninstall")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(self.installed.exists())
        for link in (self.home / ".claude/skills/duo", self.home / ".agents/skills/duo",
                     self.home / ".local/bin/duo"):
            self.assertFalse(link.is_symlink())
        self.assertTrue(other.is_dir())

    def test_duo_uninstall_runs_the_installed_copy(self):
        self.install("--from", str(ROOT))

        done = subprocess.run([str(self.home / ".local/bin/duo"), "--uninstall"], env=self.env,
                              capture_output=True, text=True, timeout=60)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("removed", done.stdout)
        self.assertFalse(self.installed.exists())
        self.assertFalse((self.home / ".local/bin/duo").is_symlink())

    def test_download_hands_over_to_the_newest_installer(self):
        self.env["DUO_ARCHIVE"] = self.archive()

        done = self.install()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("newest-installer-ran", done.stdout)
        self.assertIn("Downloaded the latest version", done.stdout)
        self.assertTrue((self.installed / "duo.py").is_file())

    def test_duo_update_downloads_with_the_installed_copy(self):
        self.install("--from", str(ROOT))
        self.env["DUO_ARCHIVE"] = self.archive()

        done = subprocess.run([str(self.home / ".local/bin/duo"), "-u"], env=self.env,
                              capture_output=True, text=True, timeout=60)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Updating duo", done.stdout)
        self.assertIn("newest-installer-ran", done.stdout)


if __name__ == "__main__":
    unittest.main()
