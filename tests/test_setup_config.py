import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    loader = importlib.machinery.SourceFileLoader("setup_config", str(ROOT / "setup-config"))
    spec = importlib.util.spec_from_loader("setup_config", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_config"] = module
    loader.exec_module(module)
    return module.__dict__


TOOL = load_tool()

SAMPLE = '''
# leading comment
dotfiles: true
vscode: false
agent_python_venv: "{{ lookup('env', 'HOME') }}/.local/share/default-venv"
install_mas_apps:
  - 1352778147 # Bitwarden
  - 409183694
remove_mas_apps: []
agent_python_packages: [pyyaml, requests]
nested:
  key: value
'''


class YamlSubsetTests(unittest.TestCase):
    def test_scalars_and_ignore(self):
        data = TOOL["parse_yaml_subset"]("a: true\nb: false\nc: ignore\nd: \"x y\"\n")
        self.assertIs(data["a"], True)
        self.assertIs(data["b"], False)
        self.assertEqual(data["c"], "ignore")
        self.assertEqual(data["d"], "x y")

    def test_block_list_keeps_inline_comments(self):
        data = TOOL["parse_yaml_subset"](SAMPLE)
        items = data["install_mas_apps"]
        self.assertEqual([(i.value, i.comment) for i in items],
                         [("1352778147", "Bitwarden"), ("409183694", None)])

    def test_flow_lists_and_empty_list(self):
        data = TOOL["parse_yaml_subset"](SAMPLE)
        self.assertEqual([i.value for i in data["agent_python_packages"]], ["pyyaml", "requests"])
        self.assertEqual(data["remove_mas_apps"], [])

    def test_nested_mapping_is_unsupported(self):
        data = TOOL["parse_yaml_subset"](SAMPLE)
        self.assertIsInstance(data["nested"], TOOL["UnsupportedValue"])

    def test_split_blocks_keeps_comments_as_trivia(self):
        blocks = TOOL["split_blocks"]("# header\n\ndotfiles: true\n\n# about vscode\nvscode: false\n")
        self.assertEqual([(b.key, len(b.lines)) for b in blocks],
                         [(None, 2), ("dotfiles", 1), (None, 2), ("vscode", 1)])


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.defaults = TOOL["parse_yaml_subset"]((ROOT / "default.config.yml").read_text())
        self.menu = TOOL["load_menu"](ROOT / "setup-config-menu.json", self.defaults)

    def test_categories_and_counts(self):
        self.assertEqual([c.id for c in self.menu.categories], ["groups", "system", "macos"])
        self.assertEqual(len(self.menu.categories[0].items), 11)
        self.assertEqual(len(self.menu.categories[1].items), 8)
        self.assertEqual(len(self.menu.categories[2].items), 4)

    def test_prefer_homebrew_toggle(self):
        items = {i.key: i for c in self.menu.categories for i in c.items}
        self.assertIn("prefer_homebrew", items)
        self.assertEqual(items["prefer_homebrew"].kind, "bool")
        self.assertIs(self.defaults["prefer_homebrew"], True)

    def test_package_keys_cover_read_only_lists(self):
        self.assertIn("agent_python_packages", self.menu.package_keys)
        self.assertIn("install_mas_apps", self.menu.package_keys)
        self.assertIn("remove_mas_apps", self.menu.package_keys)
        for category in self.menu.categories:
            for item in category.items:
                for key in item.lists:
                    self.assertIn(key, self.menu.package_keys)

    def test_duplicate_keys_are_rejected(self):
        item = TOOL["MenuItem"]("dotfiles", "Dotfiles", "x", "bool")
        menu = TOOL["Menu"]((TOOL["Category"]("a", "A", (item, item)),), ())
        errors = TOOL["validate_menu"](menu, self.defaults)
        self.assertTrue(any("duplicate" in e.lower() for e in errors))

    def test_unknown_key_and_type_mismatch_are_rejected(self):
        unknown = TOOL["MenuItem"]("nope", "Nope", "x", "bool")
        wrong = TOOL["MenuItem"]("dotfiles", "Dotfiles", "x", "string")
        menu = TOOL["Menu"]((TOOL["Category"]("a", "A", (unknown, wrong)),), ())
        errors = TOOL["validate_menu"](menu, self.defaults)
        self.assertTrue(any("unknown" in e.lower() for e in errors))
        self.assertTrue(any("type" in e.lower() for e in errors))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.defaults = self.dir / "default.config.yml"
        self.defaults.write_text(
            "dotfiles: true\n"
            "vscode: false\n"
            "agent_python_venv: \"{{ lookup('env', 'HOME') }}/venv\"\n"
            "install_mas_apps:\n  - 1352778147 # Bitwarden\n"
            "sync_casks:\n  - nextcloud\n"
        )
        self.prefs = self.dir / ".setup-options"
        self.package_keys = ("install_mas_apps", "sync_casks")

    def config(self):
        return TOOL["Config"](self.defaults, self.prefs, self.package_keys)

    def test_effective_and_source(self):
        self.prefs.write_text("vscode: true\n")
        cfg = self.config()
        self.assertIs(cfg.effective("vscode"), True)
        self.assertEqual(cfg.source("vscode"), "override")
        self.assertIs(cfg.effective("dotfiles"), True)
        self.assertEqual(cfg.source("dotfiles"), "default")

    def test_set_writes_override_and_preserves_file(self):
        self.prefs.write_text("# keep me\n\ninstall_mas_apps:\n  - 1352778147 # Bitwarden\n# trailing\n")
        cfg = self.config()
        self.assertTrue(cfg.set("dotfiles", False))
        text = self.prefs.read_text()
        self.assertIn("# keep me", text)
        self.assertIn("# trailing", text)
        self.assertIn("dotfiles: false", text)
        self.assertIn("- 1352778147 # Bitwarden", text)

    def test_set_default_removes_override(self):
        self.prefs.write_text("dotfiles: false\n")
        cfg = self.config()
        self.assertTrue(cfg.set("dotfiles", True))
        self.assertNotIn("dotfiles", self.prefs.read_text())
        self.assertEqual(cfg.source("dotfiles"), "default")

    def test_reset_keeps_nearby_comment(self):
        self.prefs.write_text("# about vscode\nvscode: true\n")
        cfg = self.config()
        self.assertTrue(cfg.reset("vscode"))
        self.assertIn("# about vscode", self.prefs.read_text())
        self.assertNotIn("vscode:", self.prefs.read_text())

    def test_noop_does_not_create_file(self):
        cfg = self.config()
        self.assertFalse(cfg.set("dotfiles", True))
        self.assertFalse(self.prefs.exists())

    def test_clear_package_overrides_removes_only_package_keys(self):
        self.prefs.write_text(
            "dotfiles: false\n"
            "sync_casks:\n  - nextcloud\n"
            "install_mas_apps:\n  - 1352778147 # Bitwarden\n"
        )
        cfg = self.config()
        removed = cfg.clear_package_overrides()
        self.assertEqual(set(removed), {"sync_casks", "install_mas_apps"})
        text = self.prefs.read_text()
        self.assertIn("dotfiles: false", text)
        self.assertNotIn("sync_casks", text)
        self.assertNotIn("install_mas_apps", text)
        self.assertTrue((self.dir / ".setup-options.bak").exists())

    def test_unsupported_managed_value_is_not_rewritten(self):
        self.prefs.write_text("dotfiles:\n  nested: true\n")
        cfg = self.config()
        self.assertIn("dotfiles", cfg.unsupported_keys())
        with self.assertRaises(TOOL["ConfigError"]):
            cfg.set("dotfiles", False)
        self.assertIn("nested: true", self.prefs.read_text())

    def test_creates_file_with_header(self):
        cfg = self.config()
        self.assertTrue(cfg.set("vscode", True))
        self.assertTrue(self.prefs.read_text().startswith("# Local overrides"))

    def test_ignore_allowed_for_tristate_keys(self):
        cfg = TOOL["Config"](self.defaults, self.prefs, self.package_keys, ("dotfiles",))
        self.assertTrue(cfg.set("dotfiles", "ignore"))
        self.assertIn("dotfiles: ignore", self.prefs.read_text())


from types import SimpleNamespace
from unittest import mock


class FakeTTY:
    def __init__(self, value):
        self.value = value
    def isatty(self):
        return self.value


class ApplyTests(unittest.TestCase):
    def test_build_apply_command(self):
        self.assertEqual(
            TOOL["build_apply_command"]("/x/ansible-playbook"),
            ["/x/ansible-playbook", "-i", "localhost,", "-c", "local", "main.yml"],
        )

    def test_build_apply_command_can_request_become_password(self):
        self.assertEqual(
            TOOL["build_apply_command"]("/x/ansible-playbook", ask_become_pass=True),
            [
                "/x/ansible-playbook",
                "-i",
                "localhost,",
                "-c",
                "local",
                "--ask-become-pass",
                "main.yml",
            ],
        )

    def test_become_prompt_is_only_needed_for_apt(self):
        self.assertTrue(TOOL["become_prompt_required"](True))
        self.assertFalse(TOOL["become_prompt_required"](False))

    def test_become_choice_requires_an_explicit_yes(self):
        self.assertTrue(TOOL["become_choice_confirmed"](True))
        self.assertFalse(TOOL["become_choice_confirmed"](False))
        self.assertFalse(TOOL["become_choice_confirmed"](None))

    def test_apply_playbook_forwards_become_flag(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0)

        code = TOOL["apply_playbook"](
            ROOT,
            runner=runner,
            which=lambda name: "/fake/ansible-playbook",
            out=lambda line: None,
            ask_become_pass=True,
        )
        self.assertEqual(code, 0)
        self.assertIn("--ask-become-pass", calls[0])

    def test_missing_ansible_returns_127(self):
        out = []
        code = TOOL["apply_playbook"](
            ROOT, which=lambda name: None, is_executable=lambda path, mode: False, out=out.append
        )
        self.assertEqual(code, 127)
        self.assertTrue(any("not found" in line for line in out))

    def test_missing_playbook_returns_1(self):
        out = []
        with tempfile.TemporaryDirectory() as tmp:
            code = TOOL["apply_playbook"](
                Path(tmp), which=lambda name: "/fake/ansible-playbook", out=out.append
            )
        self.assertEqual(code, 1)
        self.assertTrue(any("main.yml" in line for line in out))

    def test_apply_uses_repo_root_and_returns_code(self):
        calls = []
        def runner(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(returncode=5)
        code = TOOL["apply_playbook"](
            ROOT, runner=runner, which=lambda name: "/fake/ansible-playbook", out=lambda line: None
        )
        self.assertEqual(code, 5)
        self.assertEqual(calls[0][0], ["/fake/ansible-playbook", "-i", "localhost,", "-c", "local", "main.yml"])
        self.assertEqual(calls[0][1]["cwd"], str(ROOT))

    def test_apply_now_propagates_exit_code(self):
        with mock.patch.dict(
            TOOL,
            {"apply_playbook": lambda repo_root, **kwargs: 7, "apt_available": lambda: False},
        ):
            self.assertEqual(TOOL["main"](["--apply-now"]), 7)

    def test_ask_become_pass_requires_apply_now(self):
        with self.assertRaises(SystemExit) as ctx:
            TOOL["main"](["--ask-become-pass"])
        self.assertEqual(ctx.exception.code, 2)

    def test_apply_now_propagates_ask_become_pass(self):
        calls = []

        def fake_apply(repo_root, **kwargs):
            calls.append((repo_root, kwargs))
            return 0

        with mock.patch.dict(TOOL, {"apply_playbook": fake_apply}):
            self.assertEqual(
                TOOL["main"](["--apply-now", "--ask-become-pass"]), 0
            )
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][1].get("ask_become_pass"), True)

    def test_non_tty_interactive_mode_returns_2(self):
        with mock.patch.object(TOOL["sys"], "stdin", FakeTTY(False)):
            with mock.patch.object(TOOL["sys"], "stdout", FakeTTY(True)):
                self.assertEqual(TOOL["main"]([]), 2)


class CliTests(unittest.TestCase):
    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            TOOL["main"](["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_unknown_argument_exits_two(self):
        with self.assertRaises(SystemExit) as ctx:
            TOOL["main"](["--nope"])
        self.assertEqual(ctx.exception.code, 2)


class UiHelperTests(unittest.TestCase):
    def test_cycle_tristate_and_labels(self):
        self.assertIs(TOOL["cycle_tristate"](True), "ignore")
        self.assertIs(TOOL["cycle_tristate"]("ignore"), False)
        self.assertIs(TOOL["cycle_tristate"](False), True)
        self.assertEqual([TOOL["status_label"](v) for v in (True, "ignore", False)], ["ON", "SKIP", "OFF"])

    def test_home_formula_and_venv_normalization(self):
        home = str(Path.home())
        self.assertEqual(
            TOOL["expand_home_formula"]("{{ lookup('env', 'HOME') }}/.local/share/default-venv"),
            f"{home}/.local/share/default-venv",
        )
        self.assertEqual(TOOL["normalize_venv_path"]("~/venv"), f"{home}/venv")
        with self.assertRaises(TOOL["ToolError"]):
            TOOL["normalize_venv_path"]("relative/venv")

    def test_homebrew_available_uses_fallbacks(self):
        self.assertTrue(TOOL["homebrew_available"](
            which=lambda name: None,
            is_executable=lambda path, mode: path == "/opt/homebrew/bin/brew",
        ))
        self.assertFalse(TOOL["homebrew_available"](
            which=lambda name: None,
            is_executable=lambda path, mode: False,
        ))

    def test_homebrew_and_macos_badges(self):
        item = TOOL["MenuItem"]("mac_app_store", "Mac App Store", "x", "bool", requires="darwin")
        self.assertIn("needs Homebrew", TOOL["item_badges"](item, False, True))
        self.assertIn("macOS only", TOOL["item_badges"](item, True, False))

    def test_save_default_venv_removes_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = root / "default.config.yml"
            defaults.write_text("agent_python_venv: \"{{ lookup('env', 'HOME') }}/venv\"\n")
            prefs = root / ".setup-options"
            prefs.write_text(f"agent_python_venv: \"{Path.home()}/other\"\n")
            cfg = TOOL["Config"](defaults, prefs, ())
            self.assertTrue(TOOL["save_venv_value"](cfg, "~/venv"))
            self.assertNotIn("agent_python_venv", prefs.read_text())

    def test_format_list_and_removal_summary(self):
        item = TOOL["ListItem"]("1352778147", "Bitwarden")
        self.assertEqual(TOOL["format_list"]([item]), "1352778147 (Bitwarden)")
        self.assertEqual(TOOL["format_list"]([]), "(empty)")

    def test_wrong_type_override_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = root / "default.config.yml"
            defaults.write_text("dotfiles: true\n")
            prefs = root / ".setup-options"
            prefs.write_text("dotfiles: nope\n")
            cfg = TOOL["Config"](defaults, prefs, ())
            item = TOOL["MenuItem"]("dotfiles", "Dotfiles", "x", "bool")
            self.assertFalse(TOOL["is_editable"](item, cfg))
            text = "\n".join(TOOL["describe_item"](item, cfg, True, True))
            self.assertIn("Read-only", text)
            prefs.write_text("dotfiles:\n  nested: true\n")
            cfg = TOOL["Config"](defaults, prefs, ())
            self.assertFalse(TOOL["is_editable"](item, cfg))

    def test_describe_item_shows_value_source_and_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = root / "default.config.yml"
            defaults.write_text(
                "install_ai_dev_tools: false\n"
                "ai_dev_tools_formulae:\n  - herdr\n"
                "ai_dev_tools_casks: []\n"
            )
            prefs = root / ".setup-options"
            prefs.write_text("install_ai_dev_tools: ignore\n")
            cfg = TOOL["Config"](defaults, prefs, ())
            item = TOOL["MenuItem"](
                "install_ai_dev_tools", "AI dev tools", "x", "tristate",
                lists=("ai_dev_tools_formulae", "ai_dev_tools_casks"),
            )
            text = "\n".join(TOOL["describe_item"](item, cfg, True, True))
            self.assertIn("Value: SKIP (override)", text)
            self.assertIn("Formulae: herdr", text)

    def test_removal_summary_includes_ai_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = root / "default.config.yml"
            defaults.write_text(
                "install_ai_dev_tools: false\n"
                "ai_dev_tools_formulae:\n  - herdr\n"
                "ai_dev_tools_casks: []\n"
            )
            cfg = TOOL["Config"](defaults, root / ".setup-options", ())
            item = TOOL["MenuItem"](
                "install_ai_dev_tools", "AI dev tools", "x", "tristate",
                lists=("ai_dev_tools_formulae", "ai_dev_tools_casks"),
                extras=("opencode", "omp", "managed configs", "agent skills"),
                removals=("opencode", "omp", "managed configs"),
            )
            text = "\n".join(TOOL["removal_summary"](item, cfg))
            self.assertIn("herdr", text)
            self.assertIn("opencode", text)
            self.assertIn("omp", text)
            self.assertNotIn("agent skills", text)
