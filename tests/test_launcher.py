"""The bin/duo launcher: what each pane starts. Uses fake agents and a private tmux server."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from support import ROOT

LAUNCHER = ROOT / "bin" / "duo"
FAKE = '''#!/bin/sh
for arg in "$@"; do printf '%s\\n' "$arg"; done > "$PWD/$(basename "$0").${TMUX_PANE#%}.args"
sleep 30
'''


@unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
class Launcher(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.project = base / "my.project"
        self.project.mkdir()
        fakes = base / "fakes"
        fakes.mkdir()
        for name in ("claude", "codex"):
            fake = fakes / name
            fake.write_text(FAKE, encoding="utf-8")
            fake.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if k != "TMUX"}
        self.env.update(PATH=f"{fakes}:{os.environ['PATH']}", TMUX_TMPDIR=str(base))
        self.addCleanup(subprocess.run, ["tmux", "kill-server"], env=self.env, capture_output=True)

    def launch(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), "-d", *args], cwd=self.project, env=self.env,
                              capture_output=True, text=True, timeout=30)

    def args_of(self, name: str, panes: int = 1) -> list[list[str]]:
        """The arguments each `name` pane received, in pane order."""
        deadline = time.monotonic() + 10
        while len(list(self.project.glob(f"{name}.*.args"))) < panes and time.monotonic() < deadline:
            time.sleep(0.1)
        records = sorted(self.project.glob(f"{name}.*.args"), key=lambda p: int(p.name.split(".")[1]))
        return [r.read_text(encoding="utf-8").splitlines() for r in records]

    def test_default_pair_gets_names_and_the_task_as_data(self):
        done = self.launch('fix "quotes"; and $HOME')

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.args_of("claude"),
                         [['--settings', '{"tui":"default"}', '/duo participants: Claude and Codex; you are Claude. Task: fix "quotes"; and $HOME']])
        self.assertEqual(self.args_of("codex"),
                         [['--no-alt-screen', '$duo participants: Claude and Codex; you are Codex. Task: fix "quotes"; and $HOME']])
        self.assertIn("duo-my_project", done.stdout)

    def test_same_model_twice_gets_numbered_names_and_two_lenses(self):
        self.launch("-l", "opus", "-r", "opus", "find the leak")

        self.assertEqual(self.args_of("claude", panes=2), [
            ["--settings", '{"tui":"default"}', "--model", "opus", "/duo participants: Opus1 and Opus2; you are Opus1; lens: builder. Task: find the leak"],
            ["--settings", '{"tui":"default"}', "--model", "opus", "/duo participants: Opus1 and Opus2; you are Opus2; lens: skeptic. Task: find the leak"]])

    def test_explicit_lens_and_no_task(self):
        self.launch("-l", "opus:security", "-r", "codex")

        self.assertEqual(self.args_of("claude"),
                         [["--settings", '{"tui":"default"}', "--model", "opus", "/duo participants: Opus and Codex; you are Opus; lens: security."]])
        self.assertEqual(self.args_of("codex"), [["--no-alt-screen", "$duo participants: Opus and Codex; you are Codex."]])

    def test_two_codex_models(self):
        self.launch("-l", "codex/model-a", "-r", "codex/model-b", "compare")

        self.assertEqual(self.args_of("codex", panes=2), [
            ["--no-alt-screen", "--model", "model-a", "$duo participants: Codex1 and Codex2; you are Codex1. Task: compare"],
            ["--no-alt-screen", "--model", "model-b", "$duo participants: Codex1 and Codex2; you are Codex2. Task: compare"]])

    def test_same_codex_twice_gets_two_lenses(self):
        self.launch("-l", "codex", "-r", "codex", "compare")

        self.assertEqual(self.args_of("codex", panes=2), [
            ["--no-alt-screen", "$duo participants: Codex1 and Codex2; you are Codex1; lens: builder. Task: compare"],
            ["--no-alt-screen", "$duo participants: Codex1 and Codex2; you are Codex2; lens: skeptic. Task: compare"]])

    def test_mouse_is_on_for_the_duo_session(self):
        self.launch("task")

        mouse = subprocess.run(["tmux", "show-options", "-t", "duo-my_project", "-v", "mouse"], env=self.env,
                               capture_output=True, text=True).stdout.strip()

        self.assertEqual(mouse, "on")

    def test_a_running_session_is_not_replaced(self):
        self.launch("first")

        again = self.launch("second")

        self.assertEqual(again.returncode, 1)
        self.assertIn("already exists", again.stderr)


if __name__ == "__main__":
    unittest.main()
