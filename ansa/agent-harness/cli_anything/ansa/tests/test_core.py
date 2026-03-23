"""Unit tests for cli-anything-ansa core modules.

All tests use synthetic data — no ANSA installation required.
"""

import json
import os
import struct
import sys
import tempfile

import pytest


# ── Project tests ───────────────────────────────────────────────────

class TestProject:

    def test_create_project_default(self):
        from cli_anything.ansa.core.project import create_project
        proj = create_project("TestProject")
        assert proj["name"] == "TestProject"
        assert proj["deck"] == "NASTRAN"
        assert proj["deck_key"] == "nastran"
        assert proj["model_path"] is None
        assert proj["is_modified"] is False
        assert "created" in proj
        assert "modified" in proj

    def test_create_project_with_deck(self):
        from cli_anything.ansa.core.project import create_project, DECKS
        for deck_key, deck_name in DECKS.items():
            proj = create_project(f"Test_{deck_key}", deck=deck_key)
            assert proj["deck"] == deck_name
            assert proj["deck_key"] == deck_key

    def test_create_project_invalid_deck(self):
        from cli_anything.ansa.core.project import create_project
        with pytest.raises(ValueError, match="Unknown deck"):
            create_project("Test", deck="invalid_solver")

    def test_create_project_with_output(self, tmp_path):
        from cli_anything.ansa.core.project import create_project
        out = str(tmp_path / "project.json")
        proj = create_project("TestProject", output_path=out)
        assert os.path.isfile(out)
        with open(out) as f:
            saved = json.load(f)
        assert saved["name"] == "TestProject"
        assert saved["deck"] == "NASTRAN"

    def test_load_project(self, tmp_path):
        from cli_anything.ansa.core.project import create_project, load_project
        out = str(tmp_path / "project.json")
        create_project("LoadTest", deck="abaqus", output_path=out)
        loaded = load_project(out)
        assert loaded["name"] == "LoadTest"
        assert loaded["deck"] == "ABAQUS"
        assert "session_path" in loaded

    def test_save_project(self, tmp_path):
        from cli_anything.ansa.core.project import create_project, save_project, load_project
        out = str(tmp_path / "project.json")
        proj = create_project("SaveTest", output_path=out)
        proj["parts_count"] = 42
        save_project(proj, out)
        reloaded = load_project(out)
        assert reloaded["parts_count"] == 42

    def test_save_project_no_path(self):
        from cli_anything.ansa.core.project import create_project, save_project
        proj = create_project("NoPath")
        with pytest.raises(ValueError, match="No session path"):
            save_project(proj)

    def test_decks_completeness(self):
        from cli_anything.ansa.core.project import DECKS
        assert "nastran" in DECKS
        assert "lsdyna" in DECKS
        assert "abaqus" in DECKS
        assert len(DECKS) >= 10


# ── Session tests ───────────────────────────────────────────────────

class TestSession:

    def test_session_create(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        assert s.project is None
        assert s.history == []

    def test_session_record(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        s.record("open_model", {"path": "test.ansa"})
        assert len(s.history) == 1
        assert s.history[0]["action"] == "open_model"
        assert s.history[0]["details"]["path"] == "test.ansa"

    def test_session_undo_redo(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        s.record("action1")
        s.record("action2")
        s.record("action3")

        undone = s.undo_last()
        assert undone["action"] == "action3"

        undone2 = s.undo_last()
        assert undone2["action"] == "action2"

        redone = s.redo_last()
        assert redone["action"] == "action2"

    def test_session_undo_empty(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        assert s.undo_last() is None

    def test_session_redo_empty(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        assert s.redo_last() is None

    def test_session_save_load(self, tmp_path):
        from cli_anything.ansa.core.session import Session
        path = str(tmp_path / "session.json")
        s = Session()
        s.project = {"name": "TestProject", "deck": "NASTRAN"}
        s.record("test_action")
        s.save(path)

        s2 = Session(path)
        assert s2.project["name"] == "TestProject"
        assert len(s2.history) == 1

    def test_session_status(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        s.project = {"name": "Test", "model_path": "test.ansa"}
        status = s.status()
        assert status["project"] == "Test"
        assert status["model_path"] == "test.ansa"
        assert status["undo_available"] == 0

    def test_session_redo_cleared_on_new_action(self):
        from cli_anything.ansa.core.session import Session
        s = Session()
        s.record("a1")
        s.record("a2")
        s.undo_last()
        assert s.status()["redo_available"] == 1
        s.record("a3")
        assert s.status()["redo_available"] == 0


# ── Export tests ────────────────────────────────────────────────────

class TestExport:

    def test_list_export_formats(self):
        from cli_anything.ansa.core.export import list_export_formats
        fmts = list_export_formats()
        assert "solver_formats" in fmts
        assert "geometry_formats" in fmts
        assert "nastran" in fmts["solver_formats"]
        assert "iges" in fmts["geometry_formats"]

    def test_export_solver_invalid(self):
        from cli_anything.ansa.core.export import export_solver

        class FakeBackend:
            pass

        with pytest.raises(ValueError, match="Unknown solver"):
            export_solver(FakeBackend(), "out.dat", solver="nonexistent")

    def test_export_geometry_invalid(self):
        from cli_anything.ansa.core.export import export_geometry

        class FakeBackend:
            pass

        with pytest.raises(ValueError, match="Unknown geometry format"):
            export_geometry(FakeBackend(), "out.dat", format="nonexistent")


# ── Checks tests ────────────────────────────────────────────────────

class TestChecks:

    def test_list_check_types(self):
        from cli_anything.ansa.core.checks import list_check_types
        result = list_check_types()
        assert "check_types" in result
        names = [ct["name"] for ct in result["check_types"]]
        assert "mesh" in names
        assert "geometry" in names
        assert "penetration" in names


# ── Backend tests ───────────────────────────────────────────────────

class TestBackend:

    def test_message_header_pack_unpack(self):
        from cli_anything.ansa.utils.ansa_backend import _MessageHeader
        h = _MessageHeader(1, 0, 0, 1, 42, 100)
        packed = h.pack()
        assert len(packed) == 16
        h2 = _MessageHeader.from_bytes(packed)
        assert h2.version == 1
        assert h2.transaction_id == 42
        assert h2.length == 100

    def test_ie_pack_int(self):
        from cli_anything.ansa.utils.ansa_backend import _IE, _Tag
        ie = _IE(_Tag.result_code, 0)
        packed = ie.pack()
        assert len(packed) == 12
        tag = struct.unpack('>L', packed[:4])[0]
        assert tag == _Tag.result_code

    def test_ie_pack_string(self):
        from cli_anything.ansa.utils.ansa_backend import _IE, _Tag
        ie = _IE(_Tag.script_string, "hello")
        packed = ie.pack()
        tag = struct.unpack('>L', packed[:4])[0]
        assert tag == _Tag.script_string
        length = struct.unpack('>L', packed[4:8])[0]
        assert length == 8 + 5  # header (8) + "hello" (5)

    def test_build_script(self):
        from cli_anything.ansa.utils.ansa_backend import build_script
        script, func = build_script('print("hello")')
        assert "def main():" in script
        assert 'print("hello")' in script
        assert func == "main"
        assert "import ansa" in script

    def test_build_script_custom_imports(self):
        from cli_anything.ansa.utils.ansa_backend import build_script
        script, func = build_script('pass', imports=["import os"], function_name="run")
        assert "import os" in script
        assert "def run():" in script
        assert func == "run"

    def test_free_port(self):
        from cli_anything.ansa.utils.ansa_backend import _free_port
        port = _free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_find_ansa_not_installed(self, monkeypatch):
        from cli_anything.ansa.utils.ansa_backend import find_ansa
        monkeypatch.delenv("ANSA_HOME", raising=False)
        monkeypatch.setattr("shutil.which", lambda x: None)
        with pytest.raises(RuntimeError, match="ANSA is not installed"):
            find_ansa()

    def test_calculate_padding(self):
        from cli_anything.ansa.utils.ansa_backend import _calculate_padding
        assert _calculate_padding(4) == 0
        assert _calculate_padding(5) == 3
        assert _calculate_padding(6) == 2
        assert _calculate_padding(7) == 1
        assert _calculate_padding(8) == 0


# ── CLI tests (Click testing) ──────────────────────────────────────

class TestCLI:

    def test_cli_help(self):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "cli-anything-ansa" in result.output

    def test_cli_project_new(self, tmp_path):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        out = str(tmp_path / "test.json")
        result = runner.invoke(cli, ["project", "new", "-n", "Test", "-o", out])
        assert result.exit_code == 0
        assert os.path.isfile(out)

    def test_cli_project_new_json(self, tmp_path):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        out = str(tmp_path / "test.json")
        result = runner.invoke(cli, ["--json", "project", "new", "-n", "Test", "-o", out])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Test"

    def test_cli_export_formats(self):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "export", "formats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "solver_formats" in data

    def test_cli_checks_list(self):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "checks", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "check_types" in data

    def test_cli_session_status(self):
        from click.testing import CliRunner
        from cli_anything.ansa.ansa_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "session", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "history_count" in data


# ── Subprocess tests ────────────────────────────────────────────────

def _resolve_cli(name):
    """Resolve installed CLI command; falls back to python -m for dev."""
    import shutil
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = name.replace("cli-anything-", "cli_anything.") + "." + name.split("-")[-1] + "_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


class TestCLISubprocess:
    """Test the CLI as an installed command via subprocess."""

    CLI_BASE = _resolve_cli("cli-anything-ansa")

    def _run(self, args, check=True):
        import subprocess
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True,
            check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "cli-anything-ansa" in result.stdout

    def test_project_new_json(self, tmp_path):
        out = str(tmp_path / "test.json")
        result = self._run(["--json", "project", "new", "-n", "SubTest", "-o", out])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["name"] == "SubTest"
        assert os.path.isfile(out)

    def test_export_formats_json(self):
        result = self._run(["--json", "export", "formats"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "nastran" in data["solver_formats"]

    def test_checks_list_json(self):
        result = self._run(["--json", "checks", "list"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["check_types"]) >= 4

    def test_session_status_json(self):
        result = self._run(["--json", "session", "status"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "history_count" in data

    def test_project_new_and_reload(self, tmp_path):
        out = str(tmp_path / "proj.json")
        self._run(["--json", "project", "new", "-n", "Reload", "-d", "lsdyna", "-o", out])
        with open(out) as f:
            proj = json.load(f)
        assert proj["deck"] == "LSDYNA"
