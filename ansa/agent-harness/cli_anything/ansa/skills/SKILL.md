---
name: "cli-anything-ansa"
description: "CLI harness for BETA CAE Systems ANSA — CAE pre-processing, batch meshing, quality checks, and solver output via headless IAP protocol"
---

# cli-anything-ansa

CLI harness for **ANSA** pre-processor by BETA CAE Systems. Enables headless,
scriptable access to ANSA operations via the Inter-ANSA Protocol (IAP).

## Prerequisites

- ANSA v22+ installed
- `ANSA_HOME` environment variable set to the installation directory

## Installation

```bash
cd ansa/agent-harness
pip install -e .
```

## Command Groups

### project — Model management
```bash
cli-anything-ansa project new -n "MyModel" -d nastran -o project.json
cli-anything-ansa --project project.json project open model.ansa
cli-anything-ansa --project project.json project save
cli-anything-ansa --project project.json project info
```

### mesh — Batch meshing
```bash
cli-anything-ansa --project project.json mesh batch -p params.ansa_mpar -q quality.ansa_qual
cli-anything-ansa --project project.json mesh run
cli-anything-ansa --project project.json mesh stats -o report.html
```

### export — Solver and geometry output
```bash
cli-anything-ansa --project project.json export solver output.nas -f nastran
cli-anything-ansa --project project.json export solver output.k -f lsdyna
cli-anything-ansa --project project.json export geometry output.iges -f iges
cli-anything-ansa --json export formats
```

### checks — Quality checks
```bash
cli-anything-ansa --project project.json checks run -t mesh
cli-anything-ansa --project project.json checks run -t geometry -o report.html
cli-anything-ansa --json checks list
```

### connections — Weld/bolt management
```bash
cli-anything-ansa --project project.json connections read weldfile.vip -f VIP
cli-anything-ansa --project project.json connections realize
cli-anything-ansa --json --project project.json connections list
```

### session — Session state
```bash
cli-anything-ansa --json session status
cli-anything-ansa --json session history
cli-anything-ansa session new --discard
```

### script — Custom scripts
```bash
cli-anything-ansa script my_script.py -f main
```

## Agent Usage

- Use `--json` flag on all commands for machine-parseable output
- Use `--project <path>` to maintain state across commands
- The CLI launches ANSA in listener mode automatically on first backend command
- Export formats: nastran, lsdyna, abaqus, pamcrash, radioss, ansys, permas, optistruct, marc
- Geometry formats: iges, stl, step
