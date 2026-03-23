"""Quality checks — run mesh and geometry quality checks via ANSA."""


def run_quality_checks(backend, check_type="mesh", deck="NASTRAN",
                       output_path=None):
    """Run quality checks on the current model.

    Args:
        backend: AnsaProcess instance.
        check_type: Type of check (mesh, geometry, penetration, general).
        deck: Solver deck constant name.
        output_path: Optional path to save check report.

    Returns:
        dict with check results.
    """
    report_line = ""
    if output_path:
        import os
        p = os.path.abspath(output_path).replace("\\", "/")
        report_line = f'''
    from ansa import report
    report.SaveHtmlReport("{p}")'''

    script = f'''import ansa
from ansa import base, constants
from ansa.base import checks

def main():
    deck = constants.{deck}
    entities = base.CollectEntities(deck, None, "SHELL")
    entities += base.CollectEntities(deck, None, "SOLID")

    results = checks.{check_type}.CheckEntities(entities, deck)

    total = len(entities)
    failed = len(results) if results else 0
    passed = total - failed
{report_line}

    return {{
        "status": "ok",
        "check_type": "{check_type}",
        "total_entities": str(total),
        "passed": str(passed),
        "failed": str(failed),
    }}
'''
    return backend.run_script(script, "main")


def list_check_types():
    """List available quality check types."""
    return {
        "check_types": [
            {"name": "mesh", "description": "Mesh quality checks (aspect ratio, skewness, warpage, etc.)"},
            {"name": "geometry", "description": "Geometry quality checks (gaps, overlaps, free edges)"},
            {"name": "penetration", "description": "Penetration/intersection checks"},
            {"name": "general", "description": "General model checks"},
        ]
    }
