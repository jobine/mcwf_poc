"""End-to-end tests for cli-anything-ansa.

These tests require a running ANSA installation (ANSA_HOME must be set).
They test the full pipeline: start ANSA → open model → mesh → export → verify.
"""

import json
import os
import subprocess
import sys
import time

import pytest


# Skip all E2E tests if ANSA is not installed
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANSA_HOME"),
    reason="ANSA_HOME not set — ANSA is required for E2E tests"
)


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


class TestAnsaBackendConnection:
    """Test direct backend connection to ANSA."""

    def test_start_and_connect(self):
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        with AnsaProcess(timeout=120) as proc:
            result = proc.run_script(
                'def main():\n    return {"status": "ok"}',
                "main"
            )
            assert result["success"]
            assert result["result"]["status"] == "ok"

    def test_collect_entities_empty(self):
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        with AnsaProcess(timeout=120) as proc:
            result = proc.run_script('''
import ansa
from ansa import base, constants, session

def main():
    session.New("discard")
    parts = base.CollectEntities(constants.NASTRAN, None, "ANSAPART")
    return {"parts_count": str(len(parts))}
''', "main")
            assert result["success"]
            # ANSA creates a default ANSAPART in a new session
            assert int(result["result"]["parts_count"]) <= 1


class TestProjectE2E:
    """Test project operations with real ANSA backend."""

    def test_new_session(self):
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        from cli_anything.ansa.core.project import new_session
        with AnsaProcess(timeout=120) as proc:
            result = new_session(proc, discard=True)
            assert result["success"]

    def test_get_model_info_empty(self):
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        from cli_anything.ansa.core.project import get_model_info, new_session
        with AnsaProcess(timeout=120) as proc:
            new_session(proc)
            result = get_model_info(proc)
            assert result["success"]
            # ANSA creates a default ANSAPART in a new session
            assert int(result["result"]["parts_count"]) <= 1


class TestExportE2E:
    """Test export operations with real ANSA backend."""

    def test_export_empty_nastran(self, tmp_path):
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        from cli_anything.ansa.core.project import new_session
        from cli_anything.ansa.core.export import export_solver

        out = str(tmp_path / "empty.nas")
        with AnsaProcess(timeout=120) as proc:
            new_session(proc)
            result = export_solver(proc, out, "nastran")
            assert result["success"]
            # File may or may not be created for empty model
            print(f"\n  Nastran: {out} ({result['result'].get('file_size', 'N/A')} bytes)")


class TestCLISubprocessE2E:
    """Test the CLI command via subprocess with real ANSA."""

    CLI_BASE = _resolve_cli("cli-anything-ansa")

    def _run(self, args, check=True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True,
            check=check,
            timeout=300,
        )

    def test_project_new_open_info(self, tmp_path):
        proj_path = str(tmp_path / "e2e.json")

        # Create project
        result = self._run(["--json", "project", "new", "-n", "E2E_Test", "-o", proj_path])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["name"] == "E2E_Test"

        # Get info (will start ANSA)
        result = self._run(["--json", "--project", proj_path, "project", "info"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        print(f"\n  Model info: {data}")

    def test_full_workflow(self, tmp_path):
        """Full workflow: new project → new session → export."""
        proj_path = str(tmp_path / "workflow.json")
        nas_path = str(tmp_path / "output.nas")

        # Create project
        self._run(["--json", "project", "new", "-n", "Workflow", "-o", proj_path])

        # Start new session
        result = self._run(["--json", "--project", proj_path, "session", "new"])
        assert result.returncode == 0

        # Export (empty model)
        result = self._run([
            "--json", "--project", proj_path,
            "export", "solver", nas_path, "-f", "nastran"
        ])
        assert result.returncode == 0
        print(f"\n  Nastran export: {nas_path}")
