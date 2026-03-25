"""Batch meshing operations for ANSA."""

import os


def create_batch_session(backend, session_name="default",
                         params_file=None, quality_file=None,
                         deck="NASTRAN"):
    """Create a batch mesh session and optionally load parameters.

    Args:
        backend: AnsaProcess instance.
        session_name: Name for the batch mesh session.
        params_file: Path to .ansa_mpar mesh parameters file.
        quality_file: Path to .ansa_qual quality criteria file.
        deck: Solver deck constant name.

    Returns:
        dict with session creation result.
    """
    params_load = ""
    if params_file:
        p = os.path.abspath(params_file).replace("\\", "/")
        params_load = f'    batchmesh.ReadSessionMeshParams(session, "{p}")\n'

    quality_load = ""
    if quality_file:
        q = os.path.abspath(quality_file).replace("\\", "/")
        quality_load = f'    batchmesh.ReadSessionQualityCriteria(session, "{q}")\n'

    script = f'''import ansa
from ansa import base, constants, batchmesh

def main():
    session = batchmesh.GetNewSession("Name", "{session_name}")
{params_load}{quality_load}
    parts = base.CollectEntities(constants.{deck}, None, "ANSAPART")
    for part in parts:
        batchmesh.AddPartToSession(part, session)

    return {{
        "status": "ok",
        "session_name": "{session_name}",
        "parts_added": str(len(parts)),
    }}
'''
    return backend.run_script(script, "main")


def run_batch_session(backend, session_name="default", timeout_minutes=120):
    """Run a previously created batch mesh session.

    Args:
        backend: AnsaProcess instance.
        session_name: Name of the session to run.
        timeout_minutes: Max minutes to wait for meshing.

    Returns:
        dict with run result.
    """
    script = f'''import ansa
from ansa import batchmesh

def main():
    # Run the session (uses the most recently created session)
    session = batchmesh.GetNewSession("Name", "{session_name}")
    status = batchmesh.RunSession(session)
    result = {{
        "status": "ok" if status == 1 else "failed",
        "run_status": str(status),
    }}
    return result
'''
    return backend.run_script(script, "main")


def get_mesh_statistics(backend, output_path=None, session_name="default"):
    """Get mesh statistics and optionally export report.

    Args:
        backend: AnsaProcess instance.
        output_path: Optional path for HTML statistics report.
        session_name: Session name.

    Returns:
        dict with mesh statistics.
    """
    export_line = ""
    if output_path:
        p = os.path.abspath(output_path).replace("\\", "/")
        export_line = f'    batchmesh.WriteStatistics(session, "{p}")\n'

    script = f'''import ansa
from ansa import base, constants, batchmesh

def main():
    session = batchmesh.GetNewSession("Name", "{session_name}")
{export_line}
    nodes = base.CollectEntities(constants.NASTRAN, None, "NODE")
    shells = base.CollectEntities(constants.NASTRAN, None, "SHELL")
    solids = base.CollectEntities(constants.NASTRAN, None, "SOLID")

    return {{
        "status": "ok",
        "nodes_count": str(len(nodes)),
        "shells_count": str(len(shells)),
        "solids_count": str(len(solids)),
    }}
'''
    return backend.run_script(script, "main")


def add_mesh_filter(backend, session_name, field, operator, value,
                    match_mode="any"):
    """Add a filter to a batch mesh session to select parts.

    Args:
        backend: AnsaProcess instance.
        session_name: Session to add filter to.
        field: Filter field (e.g., "Module Id", "COG x").
        operator: Filter operator (e.g., "is less than", "is in range x/y").
        value: Filter value.
        match_mode: "any" or "all".
    """
    script = f'''import ansa
from ansa import batchmesh

def main():
    session = batchmesh.GetNewSession("Name", "{session_name}")
    batchmesh.AddFilterToSession("{field}", "{operator}", "{value}",
                                 session, "Match", "{match_mode}")
    return {{"status": "ok"}}
'''
    return backend.run_script(script, "main")
