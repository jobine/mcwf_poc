"""Project management — open, save, close, info for ANSA models."""

import json
import os
from pathlib import Path
import time

from app.core.ansa_backend import (
    _is_backend_result_ok,
    _backend_result_error,
    _resolve_script_content,
)


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


def open_model(backend, model_path, project=None, quiet_period_ms: int = 200, quiet_max_wait_ms: int = 1200):
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
        script=script,
        function_name="main",
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

