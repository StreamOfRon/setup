"""Integration tests for playbook task files.

These run a small play through ansible-playbook with a temporary HOME and a
PATH that deliberately excludes the managed binaries. That reproduces a
first apply on a fresh machine: the install step may have just happened, but
the command lookup that follows must not decide whether configuration is
written.
"""

import json
import os
import re
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
          os_family: Debian
          system: "{{ fake_system }}"
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
            "fake_system": "Linux",
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

        config = self.home / ".config/ghostty/config.ghostty"
        self.assertTrue(config.exists(), "ghostty config was not written on first run")
        self.assertIn("font-family=FiraCode Nerd Font", config.read_text())

    def test_ghostty_config_uses_the_macos_application_support_path(self):
        self.run_tasks(
            "tasks/ghostty.yml",
            {"install_ghostty": True, "fake_system": "Darwin"},
        )

        config = self.home / "Library/Application Support/com.mitchellh.ghostty/config.ghostty"
        self.assertTrue(config.exists(), "ghostty config was not written for macOS")
        self.assertFalse(
            (self.home / ".config/ghostty").exists(),
            "ghostty config must not be written to the XDG path on macOS",
        )

    def test_ghostty_removal_runs_when_the_group_is_off(self):
        config = self.home / ".config/ghostty/config.ghostty"
        config.parent.mkdir(parents=True)
        config.write_text("# stale\n")

        self.run_tasks("tasks/ghostty.yml", {"install_ghostty": False})

        self.assertFalse(config.exists(), "ghostty config was not removed when OFF")

    def test_ghostty_removal_uses_the_macos_application_support_path(self):
        config = self.home / "Library/Application Support/com.mitchellh.ghostty/config.ghostty"
        config.parent.mkdir(parents=True)
        config.write_text("# stale\n")

        self.run_tasks(
            "tasks/ghostty.yml",
            {"install_ghostty": False, "fake_system": "Darwin"},
        )

        self.assertFalse(config.exists(), "macOS ghostty config was not removed when OFF")

    def test_ghostty_removal_cleans_up_the_legacy_config_path(self):
        legacy = self.home / ".config/ghostty/ghostty.conf"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# stale\n")

        self.run_tasks("tasks/ghostty.yml", {"install_ghostty": False})

        self.assertFalse(legacy.exists(), "legacy ghostty config was not removed when OFF")

    def test_ghostty_ignore_leaves_existing_config_alone(self):
        config = self.home / ".config/ghostty/config.ghostty"
        config.parent.mkdir(parents=True)
        config.write_text("# hand written\n")

        self.run_tasks("tasks/ghostty.yml", {"install_ghostty": "ignore"})

        self.assertEqual(config.read_text(), "# hand written\n")

    def test_worktrunk_and_herdr_config_are_written_without_binaries(self):
        self.run_tasks("tasks/herdr.yml", {"install_ai_dev_tools": True})

        worktrunk = self.home / ".config/worktrunk/config.toml"
        herdr = self.home / ".config/herdr/config.toml"
        self.assertTrue(worktrunk.exists(), "worktrunk config was not written")
        self.assertTrue(herdr.exists(), "herdr config was not written")
        self.assertIn("worktrunk.open", herdr.read_text())

    def test_ignore_is_inert_for_package_files(self):
        # If the tristate gate were wrong this would attempt apt with no
        # become password and fail.
        self.run_tasks(
            "tasks/apt_packages.yml",
            {
                "fake_pkg_mgr": "apt",
                "enabled": "ignore",
                "groupname": "test",
                "packages": ["zstd"],
            },
        )


class ZshrcIncludeTests(TaskFileTests):
    """The playbook manages ~/.zshrc by include, never by rewriting it."""

    SETUP_LINE = "[[ ! -f ~/.zshrc.setup ]] || source ~/.zshrc.setup"
    LOCAL_LINE = "[[ ! -f ~/.zshrc.local ]] || source ~/.zshrc.local"

    def test_fresh_machine_gets_the_include_before_the_local_override(self):
        self.run_tasks("tasks/dotfiles.yml")

        zshrc = (self.home / ".zshrc").read_text()
        self.assertIn(self.SETUP_LINE, zshrc)
        self.assertIn(self.LOCAL_LINE, zshrc)
        self.assertLess(
            zshrc.index(self.SETUP_LINE),
            zshrc.index(self.LOCAL_LINE),
            "the setup include must be sourced before the local override",
        )

    def test_setup_include_file_is_written_without_the_local_override(self):
        self.run_tasks("tasks/dotfiles.yml")

        include = (self.home / ".zshrc.setup").read_text()
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', include)
        self.assertNotIn(
            ".zshrc.local", include, "the local override lives in .zshrc itself"
        )

    def test_setup_line_is_inserted_before_an_existing_local_line(self):
        (self.home / ".zshrc").write_text(
            "export PATH=\"$HOME/bin:$PATH\"\n"
            "alias ll='ls -l'\n"
            + self.LOCAL_LINE + "\n"
        )

        self.run_tasks("tasks/dotfiles.yml")

        lines = (self.home / ".zshrc").read_text().splitlines()
        self.assertEqual(
            lines,
            [
                "export PATH=\"$HOME/bin:$PATH\"",
                "alias ll='ls -l'",
                self.SETUP_LINE,
                self.LOCAL_LINE,
            ],
        )

    def test_a_user_placed_setup_line_is_not_moved(self):
        (self.home / ".zshrc").write_text(
            "# my personal rc\n"
            + self.SETUP_LINE + "\n"
            "alias gs='git status'\n"
            + self.LOCAL_LINE + "\n"
        )

        self.run_tasks("tasks/dotfiles.yml")

        lines = (self.home / ".zshrc").read_text().splitlines()
        self.assertEqual(
            lines,
            [
                "# my personal rc",
                self.SETUP_LINE,
                "alias gs='git status'",
                self.LOCAL_LINE,
            ],
        )

    def test_zshrc_template_does_not_source_the_local_override(self):
        template = (ROOT / "templates/zshrc.j2").read_text()
        self.assertNotIn(
            ".zshrc.local",
            template,
            "the local override line is owned by the .zshrc tasks",
        )


class GhosttyConfigFileTests(unittest.TestCase):
    """Ghostty rejects unknown keys and missing theme names at load time."""

    # Options verified against https://ghostty.org/docs/config/reference.
    KNOWN_OPTIONS = {
        "cursor-style",
        "font-family",
        "shell-integration",
        "term",
        "window-padding-x",
        "window-padding-y",
        "background-opacity",
        "background-blur",
        "link-url",
        "copy-on-select",
    }

    def options(self):
        options = {}
        for line in (ROOT / "files/ghostty.conf").read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("{%") or stripped.startswith("{#") or stripped.startswith("{{"):
                continue
            key, _, value = stripped.partition("=")
            options[key.strip()] = value.strip()
        return options

    def test_uses_only_documented_options(self):
        unknown = sorted(set(self.options()) - self.KNOWN_OPTIONS)
        self.assertEqual(unknown, [], f"unknown Ghostty options: {unknown}")

    def test_leaves_the_theme_to_ghostty(self):
        # There is no built-in theme named "dark"; unset means Ghostty follows
        # the system light/dark appearance with its own colors.
        self.assertNotIn("theme", self.options())


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


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _walk_tasks(tasks, inherited_whens=()):
    """Yield (task, conditions) with block-level conditions inherited."""
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        whens = list(inherited_whens) + _as_list(task.get("when"))
        yield task, whens
        for key in ("block", "rescue", "always"):
            yield from _walk_tasks(task.get(key), whens)


BECOME_GATE = "ansible_become_password is defined"


class GroupDefaultTests(unittest.TestCase):
    """A fresh checkout must install and remove nothing."""

    def test_tristate_package_groups_default_to_ignore(self):
        menu = json.loads((ROOT / "setup-config-menu.json").read_text())
        groups = [
            item
            for category in menu["categories"]
            for item in category["items"]
            if item["type"] == "tristate"
        ]
        self.assertTrue(groups, "no tristate groups found in the menu")

        config = (ROOT / "default.config.yml").read_text()
        for item in groups:
            match = re.search(
                rf"^{re.escape(item['key'])}:\s*(\S+)", config, re.MULTILINE
            )
            self.assertIsNotNone(
                match, f"{item['key']} is missing from default.config.yml"
            )
            self.assertEqual(
                match.group(1),
                "ignore",
                f"{item['key']} must default to ignore, not {match.group(1)}",
            )


@unittest.skipUnless(yaml, "PyYAML not installed")
class BecomeGateTests(unittest.TestCase):
    def test_every_become_task_is_gated_on_a_become_password(self):
        offenders = []
        sources = [ROOT / "main.yml", *sorted((ROOT / "tasks").glob("*.yml"))]
        for path in sources:
            for document in yaml.safe_load_all(path.read_text()):
                if isinstance(document, list):
                    tasks = document
                elif isinstance(document, dict):
                    tasks = _as_list(document.get("pre_tasks")) + _as_list(
                        document.get("tasks")
                    )
                else:
                    continue
                for task, whens in _walk_tasks(tasks):
                    if task.get("become") is not True:
                        continue
                    gated = any(
                        BECOME_GATE in when for when in whens if isinstance(when, str)
                    )
                    if not gated:
                        offenders.append(
                            f"{path.name}: {task.get('name', '<unnamed>')}"
                        )
        self.assertEqual(
            offenders, [], "become without a password gate: " + ", ".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
