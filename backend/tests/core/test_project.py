"""Tests for app.core.project — project management and model operations."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.project import (
    create_project,
    load_project,
    save_project,
    open_model,
    save_model,
    get_model_info,
    new_session,
    run,
)
from app.core.ansa_backend import (
    _is_backend_result_ok,
    _backend_result_error,
    _resolve_script_content,
)


# ── Helper functions ────────────────────────────────────────────────

class TestIsBackendResultOk:
    def test_success_with_ok_status(self):
        assert _is_backend_result_ok({"success": True, "result": {"status": "ok"}}) is True

    def test_success_without_status_key(self):
        assert _is_backend_result_ok({"success": True, "result": {"data": 1}}) is True

    def test_success_no_result(self):
        assert _is_backend_result_ok({"success": True}) is True

    def test_failure(self):
        assert _is_backend_result_ok({"success": False}) is False

    def test_bad_status(self):
        assert _is_backend_result_ok({"success": True, "result": {"status": "error"}}) is False

    def test_non_dict(self):
        assert _is_backend_result_ok("bad") is False
        assert _is_backend_result_ok(None) is False


class TestBackendResultError:
    def test_error_string(self):
        msg = _backend_result_error("prefix", {"success": False, "details": "err", "result": None})
        assert "prefix" in msg
        assert "False" in msg

    def test_non_dict(self):
        msg = _backend_result_error("oops", 42)
        assert "oops" in msg
        assert "int" in msg


class TestResolveScriptContent:
    def test_string_body(self):
        assert _resolve_script_content("print('hi')") == "print('hi')"

    def test_path_object(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# from file\nprint(1)")
            f.flush()
            path = Path(f.name)
        try:
            content = _resolve_script_content(path)
            assert "# from file" in content
            # Preamble should override __file__ to the original path
            assert "__file__" in content
            assert "sys.path" in content
        finally:
            path.unlink()

    def test_string_path_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("hello_script")
            f.flush()
            name = f.name
        try:
            content = _resolve_script_content(name)
            assert "hello_script" in content
            # Preamble should be present for file-based input
            assert "__file__" in content
        finally:
            os.unlink(name)

    def test_preamble_contains_original_directory(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = Path(td) / "test_script.py"
            script_path.write_text("def main():\n    pass\n", encoding="utf-8")
            content = _resolve_script_content(script_path)
            # Preamble should add the script's directory to sys.path
            script_dir = str(script_path.parent.resolve()).replace("\\", "/")
            assert script_dir in content

    def test_no_preamble_for_inline_script(self):
        content = _resolve_script_content("def main():\n    return 1\n")
        assert "__file__" not in content
        assert "sys.path" not in content


# ── Project CRUD ────────────────────────────────────────────────────

class TestCreateProject:
    def test_defaults(self):
        p = create_project("test_proj")
        assert p["name"] == "test_proj"
        assert p["deck"] == "NASTRAN"
        assert p["deck_key"] == "nastran"
        assert p["model_path"] is None
        assert p["is_modified"] is False

    def test_custom_deck(self):
        p = create_project("p", deck="abaqus")
        assert p["deck"] == "ABAQUS"

    def test_unknown_deck_raises(self):
        with pytest.raises(ValueError, match="Unknown deck"):
            create_project("p", deck="unknown_solver")

    def test_with_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "proj.json")
            p = create_project("proj", output_path=path)
            assert "session_path" in p
            with open(path) as f:
                saved = json.load(f)
            assert saved["name"] == "proj"


class TestLoadSaveProject:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "proj.json")
            create_project("round_trip", output_path=path)
            loaded = load_project(path)
            assert loaded["name"] == "round_trip"
            assert "session_path" in loaded

    def test_save_updates_modified(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "proj.json")
            p = create_project("s", output_path=path)
            p["session_path"] = os.path.abspath(path)
            save_project(p)
            with open(path) as f:
                saved = json.load(f)
            assert "modified" in saved


# ── Model operations ────────────────────────────────────────────────

class TestOpenModel:
    def test_open_model_calls_backend(self):
        backend = MagicMock()
        backend.run_script.return_value = {
            "success": True,
            "result": {"status": "ok", "model_path": "/a/b.ansa", "parts_count": "3"},
        }
        project = create_project("test")
        open_model(backend, "/a/b.ansa", project)
        backend.run_script.assert_called_once()
        assert project["model_path"] is not None
        assert project["parts_count"] == 3

    def test_open_model_no_project(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": True, "result": {"status": "ok"}}
        open_model(backend, "/x.ansa")
        backend.run_script.assert_called_once()


class TestSaveModel:
    def test_save_as(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": True, "result": {"status": "ok"}}
        project = create_project("test")
        project["history"] = []
        save_model(backend, output_path="/tmp/out.ansa", project=project)
        backend.run_script.assert_called_once()
        assert project["is_modified"] is False

    def test_save_in_place(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": True, "result": {"status": "ok"}}
        save_model(backend)
        backend.run_script.assert_called_once()


class TestGetModelInfo:
    def test_calls_backend(self):
        backend = MagicMock()
        backend.run_script.return_value = {
            "success": True,
            "result": {"parts_count": "2", "nodes_count": "100"},
        }
        get_model_info(backend, deck="NASTRAN")
        backend.run_script.assert_called_once()


class TestNewSession:
    def test_discard(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": True, "result": {"status": "ok"}}
        new_session(backend, discard=True)
        script_arg = backend.run_script.call_args[0][0]
        assert 'discard' in script_arg

    def test_save(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": True, "result": {"status": "ok"}}
        new_session(backend, discard=False)
        script_arg = backend.run_script.call_args[0][0]
        assert 'save' in script_arg


# ── run() orchestration ─────────────────────────────────────────────

class TestRun:
    def test_run_success(self):
        backend = MagicMock()
        backend.run_script.side_effect = [
            {"success": True, "result": {"status": "ok", "model_path": "/m.ansa", "parts_count": "1"}},
            {"success": True, "result": {"status": "ok"}},
        ]
        result = run(backend, Path("/m.ansa"), "def main():\n    pass\n")
        assert result["status"] == "ok"
        assert backend.run_script.call_count == 2

    def test_run_open_fails(self):
        backend = MagicMock()
        backend.run_script.return_value = {"success": False, "result": None}
        result = run(backend, Path("/m.ansa"), "def main():\n    pass\n")
        assert result["status"] == "error"

    def test_run_script_fails(self):
        backend = MagicMock()
        backend.run_script.side_effect = [
            {"success": True, "result": {"status": "ok", "model_path": "/m.ansa", "parts_count": "1"}},
            {"success": False, "result": None},
        ]
        result = run(backend, Path("/m.ansa"), "def main():\n    pass\n")
        assert result["status"] == "error"

    def test_run_with_script_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def main():\n    return {'status': 'ok'}\n")
            f.flush()
            script_path = Path(f.name)
        try:
            backend = MagicMock()
            backend.run_script.side_effect = [
                {"success": True, "result": {"status": "ok", "model_path": "/m.ansa", "parts_count": "0"}},
                {"success": True, "result": {"status": "ok"}},
            ]
            result = run(backend, Path("/m.ansa"), script_path)
            assert result["status"] == "ok"
        finally:
            script_path.unlink()
