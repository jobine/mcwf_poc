"""Connections management — welds, adhesives, bolts via ANSA."""

import os


def read_connections(backend, connections_file, format="VIP"):
    """Read connection definitions from a file.

    Args:
        backend: AnsaProcess instance.
        connections_file: Path to connections file (.vip, .xml, etc.).
        format: Connection file format (VIP, XML).

    Returns:
        dict with read result.
    """
    abs_path = os.path.abspath(connections_file).replace("\\", "/")
    script = f'''import ansa
from ansa import connections

def main():
    connections.ReadConnections("{format}", "{abs_path}")
    return {{"status": "ok", "file": "{abs_path}", "format": "{format}"}}
'''
    return backend.run_script(script, "main")


def realize_connections(backend, deck="NASTRAN"):
    """Realize all connections in the current model.

    Args:
        backend: AnsaProcess instance.
        deck: Solver deck.

    Returns:
        dict with realization result.
    """
    script = f'''import ansa
from ansa import base, constants, connections

def main():
    deck = constants.{deck}
    conns = base.CollectEntities(deck, None, "CONNECTION_POINT")
    count = len(conns)
    if count > 0:
        connections.RealizeConnections(conns)
    return {{
        "status": "ok",
        "connections_count": str(count),
    }}
'''
    return backend.run_script(script, "main")


def list_connections(backend, deck="NASTRAN"):
    """List connections in the current model.

    Args:
        backend: AnsaProcess instance.
        deck: Solver deck.

    Returns:
        dict with connection statistics.
    """
    script = f'''import ansa
from ansa import base, constants

def main():
    deck = constants.{deck}
    conn_points = base.CollectEntities(deck, None, "CONNECTION_POINT")
    return {{
        "status": "ok",
        "connection_points": str(len(conn_points)),
    }}
'''
    return backend.run_script(script, "main")
