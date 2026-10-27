"""Integration tests for playbook task files.

These run a small play through ansible-playbook with a temporary HOME and a
PATH that deliberately excludes the managed binaries. That reproduces a
first apply on a fresh machine: the install step may have just happened, but
the command lookup that follows must not decide whether configuration is
written.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML arrives with ansible-core in CI
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_PLAYBOOK = shutil.which("ansible-playbook")

BASE_PLAY = """\
- hosts: localhost
  gather_facts: false
  tasks:
    - name: Fake package manager facts
      ansible.builtin.set_fact:
        ansible_facts:
          pkg_mgr: "{{ fake_pkg_mgr }}"
          system: Linux
          machine: x86_64
          env:
            PATH: "{{ test_path }}"

    - name: Fixture sanity check
      ansible.builtin.assert:
        that:
          - ansible_facts.pkg_mgr == fake_pkg_mgr
          - ansible_facts.env.PATH == test_path

    - name: Run the task file under test
      ansible.builtin.include_tasks: __TASK_FILE__
"""


@unittest.skipUnless(ANSIBLE_PLAYBOOK, "ansible-playbook not installed")
class TaskFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        for binary in ("herdr", "wt", "fzf"):
            stub = self.bin / binary
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        self.test_path = f"{self.bin}:{os.defpath}"
        self.play_path = ROOT / f".ansible-test-{uuid.uuid4().hex}.yml"
        self.addCleanup(lambda: self.play_path.unlink(missing_ok=True))

    def run_tasks(self, task_file, extra_vars=None):
        variables = {
            "fake_pkg_mgr": "none",
            "test_path": self.test_path,
            "ansible_python_interpreter": sys.executable,
        }
        variables.update(extra_vars or {})
        self.play_path.write_text(
            BASE_PLAY.replace("__TASK_FILE__", str(ROOT / task_file))
        )
        env = dict(os.environ)
        env.update({
            "HOME": str(self.home),
            "PATH": self.test_path,
            "ANSIBLE_LOCAL_TEMP": str(Path(self.tmp.name) / ".ansible"),
            "ANSIBLE_RETRY_FILES_ENABLED": "0",
            "ANSIBLE_NOCOLOR": "1",
            # HOME points at the fixture, so point Ansible at the collections
            # installed for the real user (CI installs community.general there).
            "ANSIBLE_COLLECTIONS_PATH": env.get(
                "ANSIBLE_COLLECTIONS_PATH",
                str(Path.home() / ".ansible" / "collections"),
            ),
        })
        cmd = [ANSIBLE_PLAYBOOK, "-i", "localhost,", "-c", "local", str(self.play_path)]
        cmd.extend(["-e", json.dumps(variables)])

        result = subprocess.run(
            cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            self.fail(
                f"ansible-playbook failed for {task_file}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

    def test_ghostty_config_is_written_before_the_binary_exists(self):
        self.run_tasks(
            "tasks/ghostty.yml",
            {"install_ghostty": True, "ghostty_install_method": "apt"},
        )

        config = self.home / ".config/ghostty/ghostty.conf"
        self.assertTrue(config.exists(), "ghostty config was not written on first run")
        self.assertIn("theme=dark", config.read_text())

    def test_ghostty_removal_runs_when_the_group_is_off(self):
        config = self.home / ".config/ghostty/ghostty.conf"
        config.parent.mkdir(parents=True)
        config.write_text("# stale\n")

        self.run_tasks("tasks/ghostty.yml", {"install_ghostty": False})

        self.assertFalse(config.exists(), "ghostty config was not removed when OFF")

    def test_worktrunk_and_herdr_config_are_written_without_binaries(self):
        self.run_tasks("tasks/herdr.yml", {"install_ai_dev_tools": True})

        worktrunk = self.home / ".config/worktrunk/config.toml"
        herdr = self.home / ".config/herdr/config.toml"
        self.assertTrue(worktrunk.exists(), "worktrunk config was not written")
        self.assertTrue(herdr.exists(), "herdr config was not written")
        self.assertIn("worktrunk.open", herdr.read_text())


@unittest.skipUnless(yaml, "PyYAML not installed")
class MainWiringTests(unittest.TestCase):
    def test_ghostty_is_managed_even_when_the_group_is_off(self):
        play = yaml.safe_load((ROOT / "main.yml").read_text())[0]
        entries = [t for t in play["tasks"] if t.get("name") == "Manage ghostty"]
        self.assertEqual(len(entries), 1, "expected exactly one ghostty entry in main.yml")

        entry = entries[0]
        self.assertFalse(
            entry.get("when"), "ghostty must be imported unconditionally so OFF can remove"
        )
        imports = [t for t in entry.get("block", []) if "ansible.builtin.import_tasks" in t]
        self.assertEqual(len(imports), 1)
        self.assertFalse(imports[0].get("when"))


if __name__ == "__main__":
    unittest.main()
