"""Project management — open, save, close, info for ANSA models."""

import json
import os
from pathlib import Path
import time


def _locked_save_json(path, data, **dump_kwargs):
    """Atomically write JSON with exclusive file locking."""
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")
    with f:
        _locked = False
        try:
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            _locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass


# ── Solver deck mapping ─────────────────────────────────────────────

DECKS = {
    "nastran": "NASTRAN",
    "lsdyna": "LSDYNA",
    "abaqus": "ABAQUS",
    "pamcrash": "PAMCRASH",
    "radioss": "RADIOSS",
    "ansys": "ANSYS",
    "permas": "PERMAS",
    "optistruct": "OPTISTRUCT",
    "marc": "MARC",
    "actran": "ACTRAN",
    "impetus": "IMPETUS",
    "fluent": "FLUENT",
    "openfoam": "OPENFOAM",
    "star": "STAR",
    "cgns": "CGNS",
}


def _is_backend_result_ok(result):
    """Return True when ANSA IAP call succeeded and payload status is ok (if present)."""
    if not isinstance(result, dict):
        return False
    if not result.get("success"):
        return False

    payload = result.get("result")
    if isinstance(payload, dict) and "status" in payload:
        return payload.get("status") == "ok"
    return True


def _backend_result_error(prefix, result):
    """Build a consistent debug-friendly error string from backend response."""
    if not isinstance(result, dict):
        return f"{prefix}: invalid result type={type(result).__name__}"
    return (
        f"{prefix}: success={result.get('success')}, "
        f"details={result.get('details')}, result={result.get('result')}"
    )


def _resolve_script_content(script):
    """Resolve script input to executable source code.

    Supports:
    - pathlib.Path / os.PathLike: read file content
    - str path to an existing file: read file content
    - str script body: use as-is
    """
    if isinstance(script, os.PathLike):
        with Path(script).open("r", encoding="utf-8") as f:
            return f.read()

    if isinstance(script, str):
        try:
            candidate = Path(script).expanduser()
            if candidate.is_file():
                with candidate.open("r", encoding="utf-8") as f:
                    return f.read()
        except (OSError, ValueError):
            pass
        return script

    return str(script)


def create_project(name, deck="nastran", output_path=None):
    """Create a new project session file.

    Args:
        name: Project name.
        deck: Solver deck (default: nastran).
        output_path: Path for the session JSON file.

    Returns:
        dict with project metadata.
    """
    deck_key = deck.lower()
    if deck_key not in DECKS:
        raise ValueError(f"Unknown deck '{deck}'. Available: {', '.join(DECKS)}")

    project = {
        "name": name,
        "deck": DECKS[deck_key],
        "deck_key": deck_key,
        "model_path": None,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "modified": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "is_modified": False,
        "history": [],
        "parts_count": 0,
        "nodes_count": 0,
        "elements_count": 0,
    }

    if output_path:
        _locked_save_json(output_path, project, indent=2)
        project["session_path"] = os.path.abspath(output_path)

    return project


def load_project(session_path):
    """Load a project from a session JSON file."""
    with open(session_path, "r") as f:
        project = json.load(f)
    project["session_path"] = os.path.abspath(session_path)
    return project


def save_project(project, path=None):
    """Save project state to session file."""
    path = path or project.get("session_path")
    if not path:
        raise ValueError("No session path specified")
    project["modified"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _locked_save_json(path, project, indent=2)
    return project


def open_model(backend, model_path, project=None, quiet_period_ms: int = 0, quiet_max_wait_ms: int = 1200):
    """Open an ANSA model file via the backend.

    Args:
        backend: AnsaProcess or AnsaConnection instance.
        model_path: Path to .ansa, .iges, .step, .nas, etc.
        project: Optional project dict to update.

    Returns:
        dict with open result.
    """
    abs_path = os.path.abspath(model_path).replace("\\", "/")
    script = f'''import ansa
from ansa import base, constants
import json

def main():
    base.Open("{abs_path}")
    parts = base.CollectEntities(constants.NASTRAN, None, "ANSAPART")
    result = {{
        "status": "ok",
        "model_path": "{abs_path}",
        "parts_count": str(len(parts)),
    }}
    return result
'''
    result = backend.run_script(
        script,
        "main",
        keep_database=False,
        quiet_period_ms=quiet_period_ms,
        quiet_max_wait_ms=quiet_max_wait_ms,
    )

    if project and result.get("result"):
        project["model_path"] = abs_path
        project["parts_count"] = int(result["result"].get("parts_count", 0))
        project["is_modified"] = False
        project["history"].append({
            "action": "open",
            "path": abs_path,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    return result


def save_model(backend, output_path=None, project=None):
    """Save the current model in ANSA.

    Args:
        backend: AnsaProcess or AnsaConnection instance.
        output_path: Optional path for Save As. If None, saves in place.
        project: Optional project dict to update.

    Returns:
        dict with save result.
    """
    if output_path:
        abs_path = os.path.abspath(output_path).replace("\\", "/")
        script = f'''import ansa
from ansa import base

def main():
    base.SaveAs("{abs_path}")
    return {{"status": "ok", "path": "{abs_path}"}}
'''
    else:
        script = '''import ansa
from ansa import base

def main():
    base.Save()
    return {"status": "ok"}
'''
    result = backend.run_script(script, "main")

    if project:
        if output_path:
            project["model_path"] = os.path.abspath(output_path)
        project["is_modified"] = False
        project["history"].append({
            "action": "save",
            "path": output_path or project.get("model_path", ""),
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    return result


def get_model_info(backend, deck="NASTRAN"):
    """Get information about the currently loaded model.

    Returns:
        dict with model statistics.
    """
    script = f'''import ansa
from ansa import base, constants
import json

def main():
    deck = constants.{deck}
    parts = base.CollectEntities(deck, None, "ANSAPART")
    nodes = base.CollectEntities(deck, None, "NODE")
    shells = base.CollectEntities(deck, None, "SHELL")
    solids = base.CollectEntities(deck, None, "SOLID")
    result = {{
        "parts_count": str(len(parts)),
        "nodes_count": str(len(nodes)),
        "shells_count": str(len(shells)),
        "solids_count": str(len(solids)),
    }}
    return result
'''
    return backend.run_script(script, "main")


def new_session(backend, discard=True):
    """Start a new empty session in ANSA.

    Args:
        backend: AnsaProcess or AnsaConnection instance.
        discard: If True, discard current unsaved changes.
    """
    mode = "discard" if discard else "save"
    script = f'''import ansa
from ansa import session

def main():
    session.New("{mode}")
    return {{"status": "ok"}}
'''
    return backend.run_script(script, "main")

def run(
    backend: 'AnsaProcess',
    model_path: Path,
    script: os.PathLike | str,
    project=None,
    quiet_period_ms: int = 200,
    quiet_max_wait_ms: int = 1200,
    **kwargs
):
    """Open a model and run a script on it.

    Args:
        backend: AnsaProcess instance.
        model_path: Model path to open.
        script: Script path or script content.
        project: Optional project state dict.
        quiet_period_ms: Optional stdout quiet window before returning run result.
        quiet_max_wait_ms: Max wait for quiet window.
    """
    if hasattr(backend, "start_stdout_reader"):
        backend.start_stdout_reader(callback=lambda line: print(f'[ANSA] {line}'))

    open_result = open_model(
        backend,
        model_path,
        project,
        quiet_period_ms=quiet_period_ms,
        quiet_max_wait_ms=quiet_max_wait_ms,
    )
    if not _is_backend_result_ok(open_result):
        return {"status": "error", "message": _backend_result_error("Failed to open model", open_result)}

    script_content = _resolve_script_content(script)    
    run_result = backend.run_script(
        script_content,
        "main",
        quiet_period_ms=quiet_period_ms,
        quiet_max_wait_ms=quiet_max_wait_ms,
        **kwargs
    )
    if not _is_backend_result_ok(run_result):
        return {"status": "error", "message": _backend_result_error("Script execution failed", run_result)}

    return {"status": "ok", "open_result": open_result, "run_result": run_result}


if __name__ == "__main__":
    # Example usage
    from app.core.ansa_backend import AnsaProcess

    with AnsaProcess() as ansa:
        result = run(
            backend=ansa,
            # model_path=r"D:\Code\tools\ansa\agent-harness\cli_anything\ansa\tests\data\JA10-53-010.CATProduct-s.ansa", 
            # script=r"D:\Code\tools\ansa\agent-harness\cli_anything\ansa\tests\data\part_classifier.py"
            model_path=r'D:\Workspace\mcwf_poc\backend\data\shared\demo.ansa',
            script=r'D:\Workspace\mcwf_poc\backend\scripts\part_classifier.py',
            extra_arg1='value1',
            extra_arg2=42,
        )

        print("Run result:", result)
