# cli-anything-ansa

CLI harness for **BETA CAE Systems ANSA** pre-processor. Provides headless,
scriptable access to ANSA operations via the Inter-ANSA Protocol (IAP).

## Prerequisites

- **ANSA v22+** installed (v25.1.0 recommended)
- Set `ANSA_HOME` environment variable to the ANSA installation directory:
  ```bash
  # Windows
  set ANSA_HOME=D:\Program Files (x86)\BETA_CAE_Systems\ansa_v25.1.0

  # Linux
  export ANSA_HOME=/opt/BETA_CAE_Systems/ansa_v25.1.0
  ```

## Installation

```bash
cd ansa/agent-harness
pip install -e .
```

## Usage

### One-shot commands

```bash
# Create a new project
cli-anything-ansa project new -n "MyProject" -d nastran -o project.json

# Open a model
cli-anything-ansa --project project.json project open model.ansa

# Run batch mesh
cli-anything-ansa --project project.json mesh batch -p params.ansa_mpar -q quality.ansa_qual
cli-anything-ansa --project project.json mesh run

# Export to Nastran
cli-anything-ansa --project project.json export solver output.nas -f nastran

# Run quality checks
cli-anything-ansa --project project.json checks run -t mesh

# JSON output for agents
cli-anything-ansa --json project info
```

### Interactive REPL

```bash
cli-anything-ansa
# Enters interactive mode with command history and styled prompts
```

### Execute custom scripts

```bash
cli-anything-ansa script my_script.py -f main
```

## Architecture

The CLI launches ANSA in **listener mode** (`-listenport`) and communicates
via the Inter-ANSA Protocol (IAP) over TCP sockets. Python scripts are sent
for execution, and results are returned as dictionaries.

```
CLI Command → Build Python Script → Send via IAP → ANSA Executes → Return Result
```

## Command Groups

| Group | Description |
|-------|-------------|
| `project` | Create, open, save, info for ANSA models |
| `mesh` | Batch meshing: create sessions, run, statistics |
| `export` | Output to solver decks (Nastran, LS-DYNA, etc.) and geometry (IGES, STL) |
| `checks` | Quality checks (mesh, geometry, penetration) |
| `connections` | Read, realize, list connection points |
| `session` | Session state, history, undo/redo |
| `script` | Execute arbitrary ANSA Python scripts |

## Supported Solver Decks

Nastran, LS-DYNA, Abaqus, PAM-CRASH, Radioss, ANSYS, Permas,
OptiStruct, Marc, Actran, Fluent, OpenFOAM, STAR-CCM+, and more.
