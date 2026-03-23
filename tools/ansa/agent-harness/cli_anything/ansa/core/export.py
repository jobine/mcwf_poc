"""Export operations — output solver decks and geometry formats from ANSA."""

import os


# Map of format name -> ANSA output function
_OUTPUT_FUNCTIONS = {
    "nastran": "base.OutputNastran",
    "lsdyna": "base.OutputLSDyna",
    "abaqus": "base.OutputAbaqus",
    "pamcrash": "base.OutputPamCrash",
    "radioss": "base.OutputRadioss",
    "ansys": "base.OutputAnsys",
    "permas": "base.OutputPermas",
    "optistruct": "base.OutputOptiStruct",
    "marc": "base.OutputMarc",
}

_GEOMETRY_FUNCTIONS = {
    "iges": "base.SaveFileAsIges",
    "stl": "base.OutputStl",
    "step": "base.OutputStep",
}


def export_solver(backend, output_path, solver="nastran", deck=None):
    """Export the current model to a solver deck format.

    Args:
        backend: AnsaProcess instance.
        output_path: Output file path.
        solver: Solver format name (nastran, lsdyna, abaqus, etc.).
        deck: Optional deck override.

    Returns:
        dict with export result.
    """
    solver_key = solver.lower()
    if solver_key not in _OUTPUT_FUNCTIONS:
        available = ", ".join(sorted(_OUTPUT_FUNCTIONS))
        raise ValueError(f"Unknown solver '{solver}'. Available: {available}")

    abs_path = os.path.abspath(output_path).replace("\\", "/")
    func = _OUTPUT_FUNCTIONS[solver_key]

    script = f'''import ansa
from ansa import base, constants
import os

def main():
    {func}(filename="{abs_path}")
    exists = os.path.isfile("{abs_path}")
    size = os.path.getsize("{abs_path}") if exists else 0
    return {{
        "status": "ok" if exists else "error",
        "output": "{abs_path}",
        "format": "{solver_key}",
        "file_size": str(size),
    }}
'''
    return backend.run_script(script, "main")


def export_geometry(backend, output_path, format="iges"):
    """Export geometry to an exchange format (IGES, STL, STEP).

    Args:
        backend: AnsaProcess instance.
        output_path: Output file path.
        format: Geometry format (iges, stl, step).

    Returns:
        dict with export result.
    """
    fmt_key = format.lower()
    if fmt_key not in _GEOMETRY_FUNCTIONS:
        available = ", ".join(sorted(_GEOMETRY_FUNCTIONS))
        raise ValueError(f"Unknown geometry format '{format}'. Available: {available}")

    abs_path = os.path.abspath(output_path).replace("\\", "/")
    func = _GEOMETRY_FUNCTIONS[fmt_key]

    script = f'''import ansa
from ansa import base
import os

def main():
    {func}("{abs_path}")
    exists = os.path.isfile("{abs_path}")
    size = os.path.getsize("{abs_path}") if exists else 0
    return {{
        "status": "ok" if exists else "error",
        "output": "{abs_path}",
        "format": "{fmt_key}",
        "file_size": str(size),
    }}
'''
    return backend.run_script(script, "main")


def list_export_formats():
    """List all available export formats.

    Returns:
        dict with solver and geometry format lists.
    """
    return {
        "solver_formats": sorted(_OUTPUT_FUNCTIONS.keys()),
        "geometry_formats": sorted(_GEOMETRY_FUNCTIONS.keys()),
    }
