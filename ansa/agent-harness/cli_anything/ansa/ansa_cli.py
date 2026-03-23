"""cli-anything-ansa: CLI harness for BETA CAE Systems ANSA pre-processor.

Provides a stateful CLI for ANSA operations including project management,
batch meshing, quality checks, connections, and solver output export.
Uses IAP (Inter-ANSA Protocol) to communicate with ANSA in batch/listener mode.
"""

import json
import os
import sys
import click

from cli_anything.ansa.core.project import (
    create_project, load_project, save_project,
    open_model, save_model, get_model_info, new_session, DECKS,
)
from cli_anything.ansa.core.mesh import (
    create_batch_session, run_batch_session, get_mesh_statistics,
)
from cli_anything.ansa.core.export import (
    export_solver, export_geometry, list_export_formats,
)
from cli_anything.ansa.core.checks import run_quality_checks, list_check_types
from cli_anything.ansa.core.connections import (
    read_connections, realize_connections, list_connections,
)
from cli_anything.ansa.core.session import Session


# ── Global state ────────────────────────────────────────────────────

_ansa_process = None
_session = Session()


def _output(data, as_json=False):
    """Output data as JSON or human-readable text."""
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    click.echo(f"  {k}:")
                    for k2, v2 in v.items():
                        click.echo(f"    {k2}: {v2}")
                elif isinstance(v, list):
                    click.echo(f"  {k}:")
                    for item in v:
                        if isinstance(item, dict):
                            click.echo(f"    - {item}")
                        else:
                            click.echo(f"    - {item}")
                else:
                    click.echo(f"  {k}: {v}")
        else:
            click.echo(data)


def _get_backend():
    """Get or create the ANSA backend connection."""
    global _ansa_process
    if _ansa_process is None:
        from cli_anything.ansa.utils.ansa_backend import AnsaProcess
        _ansa_process = AnsaProcess()
        _ansa_process.connect()
    return _ansa_process


# ── Main CLI group ──────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
@click.option("--project", "project_path", type=click.Path(),
              help="Path to project session file")
@click.pass_context
def cli(ctx, as_json, project_path):
    """cli-anything-ansa — CLI harness for BETA CAE Systems ANSA.

    Provides batch/headless operations for ANSA pre-processing including
    project management, meshing, quality checks, and solver output.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    ctx.obj["project_path"] = project_path

    if project_path and os.path.exists(project_path):
        ctx.obj["project"] = load_project(project_path)
    else:
        ctx.obj["project"] = None

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl, project_path=project_path)


# ── Project commands ────────────────────────────────────────────────

@cli.group()
@click.pass_context
def project(ctx):
    """Project management commands."""
    pass


@project.command("new")
@click.option("-n", "--name", required=True, help="Project name")
@click.option("-d", "--deck", default="nastran",
              type=click.Choice(list(DECKS.keys()), case_sensitive=False),
              help="Solver deck")
@click.option("-o", "--output", "output_path", type=click.Path(),
              help="Output session file path")
@click.pass_context
def project_new(ctx, name, deck, output_path):
    """Create a new project."""
    proj = create_project(name, deck, output_path)
    _session.project = proj
    _session.record("project_new", {"name": name, "deck": deck})
    _output(proj, ctx.obj["json"])


@project.command("open")
@click.argument("model_path", type=click.Path(exists=True))
@click.pass_context
def project_open(ctx, model_path):
    """Open an ANSA model file."""
    backend = _get_backend()
    result = open_model(backend, model_path, ctx.obj.get("project"))
    _session.record("open_model", {"path": model_path})
    _output(result, ctx.obj["json"])


@project.command("save")
@click.option("-o", "--output", "output_path", type=click.Path(),
              help="Save As path (optional)")
@click.pass_context
def project_save(ctx, output_path):
    """Save the current model."""
    backend = _get_backend()
    result = save_model(backend, output_path, ctx.obj.get("project"))
    _session.record("save_model", {"path": output_path})
    _output(result, ctx.obj["json"])


@project.command("info")
@click.pass_context
def project_info(ctx):
    """Show information about the current model."""
    backend = _get_backend()
    proj = ctx.obj.get("project")
    deck = proj["deck"] if proj else "NASTRAN"
    result = get_model_info(backend, deck)
    _output(result, ctx.obj["json"])


# ── Mesh commands ───────────────────────────────────────────────────

@cli.group()
@click.pass_context
def mesh(ctx):
    """Batch meshing commands."""
    pass


@mesh.command("batch")
@click.option("-n", "--name", default="default", help="Session name")
@click.option("-p", "--params", "params_file", type=click.Path(exists=True),
              help="Mesh parameters file (.ansa_mpar)")
@click.option("-q", "--quality", "quality_file", type=click.Path(exists=True),
              help="Quality criteria file (.ansa_qual)")
@click.pass_context
def mesh_batch(ctx, name, params_file, quality_file):
    """Create a batch mesh session."""
    backend = _get_backend()
    proj = ctx.obj.get("project")
    deck = proj["deck"] if proj else "NASTRAN"
    result = create_batch_session(backend, name, params_file, quality_file, deck)
    _session.record("mesh_batch", {"name": name})
    _output(result, ctx.obj["json"])


@mesh.command("run")
@click.option("-n", "--name", default="default", help="Session name to run")
@click.option("-t", "--timeout", default=120, help="Timeout in minutes")
@click.pass_context
def mesh_run(ctx, name, timeout):
    """Run a batch mesh session."""
    backend = _get_backend()
    result = run_batch_session(backend, name, timeout)
    _session.record("mesh_run", {"name": name})
    _output(result, ctx.obj["json"])


@mesh.command("stats")
@click.option("-o", "--output", "output_path", type=click.Path(),
              help="Export statistics report path")
@click.option("-n", "--name", default="default", help="Session name")
@click.pass_context
def mesh_stats(ctx, output_path, name):
    """Get mesh statistics."""
    backend = _get_backend()
    result = get_mesh_statistics(backend, output_path, name)
    _session.record("mesh_stats")
    _output(result, ctx.obj["json"])


# ── Export commands ──────────────────────────────────────────────────

@cli.group("export")
@click.pass_context
def export_group(ctx):
    """Export model to solver or geometry formats."""
    pass


@export_group.command("solver")
@click.argument("output_path", type=click.Path())
@click.option("-f", "--format", "solver", default="nastran",
              type=click.Choice(["nastran", "lsdyna", "abaqus", "pamcrash",
                                 "radioss", "ansys", "permas", "optistruct",
                                 "marc"], case_sensitive=False),
              help="Solver format")
@click.pass_context
def export_solver_cmd(ctx, output_path, solver):
    """Export to a solver deck format."""
    backend = _get_backend()
    result = export_solver(backend, output_path, solver)
    _session.record("export_solver", {"format": solver, "path": output_path})
    _output(result, ctx.obj["json"])


@export_group.command("geometry")
@click.argument("output_path", type=click.Path())
@click.option("-f", "--format", "fmt", default="iges",
              type=click.Choice(["iges", "stl", "step"], case_sensitive=False),
              help="Geometry format")
@click.pass_context
def export_geometry_cmd(ctx, output_path, fmt):
    """Export geometry to exchange format."""
    backend = _get_backend()
    result = export_geometry(backend, output_path, fmt)
    _session.record("export_geometry", {"format": fmt, "path": output_path})
    _output(result, ctx.obj["json"])


@export_group.command("formats")
@click.pass_context
def export_formats(ctx):
    """List available export formats."""
    result = list_export_formats()
    _output(result, ctx.obj["json"])


# ── Checks commands ─────────────────────────────────────────────────

@cli.group()
@click.pass_context
def checks(ctx):
    """Quality check commands."""
    pass


@checks.command("run")
@click.option("-t", "--type", "check_type", default="mesh",
              type=click.Choice(["mesh", "geometry", "penetration", "general"]),
              help="Check type")
@click.option("-o", "--output", "output_path", type=click.Path(),
              help="Report output path")
@click.pass_context
def checks_run(ctx, check_type, output_path):
    """Run quality checks."""
    backend = _get_backend()
    proj = ctx.obj.get("project")
    deck = proj["deck"] if proj else "NASTRAN"
    result = run_quality_checks(backend, check_type, deck, output_path)
    _session.record("checks_run", {"type": check_type})
    _output(result, ctx.obj["json"])


@checks.command("list")
@click.pass_context
def checks_list(ctx):
    """List available check types."""
    result = list_check_types()
    _output(result, ctx.obj["json"])


# ── Connections commands ────────────────────────────────────────────

@cli.group("connections")
@click.pass_context
def connections_group(ctx):
    """Connection management commands."""
    pass


@connections_group.command("read")
@click.argument("connections_file", type=click.Path(exists=True))
@click.option("-f", "--format", "fmt", default="VIP",
              type=click.Choice(["VIP", "XML"]),
              help="Connection file format")
@click.pass_context
def connections_read(ctx, connections_file, fmt):
    """Read connections from a file."""
    backend = _get_backend()
    result = read_connections(backend, connections_file, fmt)
    _session.record("connections_read", {"file": connections_file})
    _output(result, ctx.obj["json"])


@connections_group.command("realize")
@click.pass_context
def connections_realize(ctx):
    """Realize all connections."""
    backend = _get_backend()
    proj = ctx.obj.get("project")
    deck = proj["deck"] if proj else "NASTRAN"
    result = realize_connections(backend, deck)
    _session.record("connections_realize")
    _output(result, ctx.obj["json"])


@connections_group.command("list")
@click.pass_context
def connections_list(ctx):
    """List connections in the model."""
    backend = _get_backend()
    proj = ctx.obj.get("project")
    deck = proj["deck"] if proj else "NASTRAN"
    result = list_connections(backend, deck)
    _output(result, ctx.obj["json"])


# ── Session commands ────────────────────────────────────────────────

@cli.group("session")
@click.pass_context
def session_group(ctx):
    """Session management commands."""
    pass


@session_group.command("status")
@click.pass_context
def session_status(ctx):
    """Show current session status."""
    _output(_session.status(), ctx.obj["json"])


@session_group.command("history")
@click.pass_context
def session_history(ctx):
    """Show session history."""
    _output({"history": _session.history}, ctx.obj["json"])


@session_group.command("new")
@click.option("--discard/--save", default=True,
              help="Discard or save current changes")
@click.pass_context
def session_new(ctx, discard):
    """Start a new ANSA session."""
    backend = _get_backend()
    result = new_session(backend, discard)
    _session.record("session_new")
    _output(result, ctx.obj["json"])


# ── Script command (advanced) ───────────────────────────────────────

@cli.command("script")
@click.argument("script_file", type=click.Path(exists=True))
@click.option("-f", "--function", "func_name", default=None,
              help="Entry function name")
@click.pass_context
def run_script(ctx, script_file, func_name):
    """Execute a Python script on the ANSA backend."""
    backend = _get_backend()
    with open(script_file, "r") as f:
        script_text = f.read()
    result = backend.run_script(script_text, func_name)
    _session.record("run_script", {"file": script_file})
    _output(result, ctx.obj["json"])


# ── REPL command ────────────────────────────────────────────────────

@cli.command("repl", hidden=True)
@click.option("--project-path", type=click.Path(), default=None)
@click.pass_context
def repl(ctx, project_path):
    """Enter interactive REPL mode."""
    from cli_anything.ansa.utils.repl_skin import ReplSkin

    skin = ReplSkin("ansa", version="1.0.0")
    skin.print_banner()

    pt_session = skin.create_prompt_session()

    commands = {
        "help": "Show this help",
        "project new": "Create a new project",
        "project open <path>": "Open an ANSA model",
        "project save": "Save current model",
        "project info": "Show model info",
        "mesh batch": "Create batch mesh session",
        "mesh run": "Run batch mesh",
        "mesh stats": "Show mesh statistics",
        "export solver <path>": "Export to solver format",
        "export geometry <path>": "Export geometry",
        "checks run": "Run quality checks",
        "connections read <file>": "Read connections",
        "connections realize": "Realize connections",
        "session status": "Show session status",
        "session history": "Show action history",
        "script <file>": "Run a Python script",
        "quit": "Exit the REPL",
    }

    proj_name = ""
    if project_path and os.path.exists(project_path):
        proj = load_project(project_path)
        proj_name = proj.get("name", "")

    while True:
        try:
            line = skin.get_input(pt_session, project_name=proj_name)
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("quit", "exit", "q"):
                skin.print_goodbye()
                break
            elif cmd == "help":
                skin.help(commands)
            else:
                # Route to Click commands
                try:
                    cli.main(args=parts, standalone_mode=False,
                             parent=ctx.parent)
                except SystemExit:
                    pass
                except click.UsageError as e:
                    skin.error(str(e))
                except Exception as e:
                    skin.error(str(e))

        except (KeyboardInterrupt, EOFError):
            skin.print_goodbye()
            break


# ── Entry point ─────────────────────────────────────────────────────

def main():
    cli(obj={})


if __name__ == "__main__":
    main()
