# ANSA CLI Harness — SOP

## Software Overview

**ANSA** by BETA CAE Systems is a CAE pre-processing tool for finite element
analysis. It handles CAD import, geometry cleanup, meshing, connections,
quality checks, and solver deck output (Nastran, LS-DYNA, Abaqus, etc.).

## Backend Architecture

ANSA supports headless/batch operation via:

1. **Batch mode**: `ansa64.bat -b -script <script.py>` — runs a script and exits
2. **Listener mode**: `ansa64.bat -nolauncher -listenport <port> -foregr -b` —
   starts ANSA in listener mode, accepts remote script execution via the
   Inter-ANSA Protocol (IAP) over TCP sockets.

The CLI harness uses **listener mode** as the primary backend, keeping an ANSA
process running and sending Python scripts for execution. This enables stateful
operations (open a model, mesh it, check quality, export).

## Python API Modules

| Module | Purpose |
|--------|---------|
| `ansa.base` | Core operations: Open, Save, CollectEntities, OutputNastran, etc. |
| `ansa.mesh` | Surface and volume meshing |
| `ansa.batchmesh` | Batch meshing sessions with parameters and quality criteria |
| `ansa.connections` | Weld points, adhesives, bolts |
| `ansa.constants` | Solver deck constants (NASTRAN, LSDYNA, ABAQUS, etc.) |
| `ansa.utils` | File utilities, Merge |
| `ansa.session` | Session management (New, defbutton) |
| `ansa.cad` | CAD import/translation |
| `ansa.base.checks` | Quality checks (mesh, geometry, penetration) |
| `ansa.report` | Report generation |
| `ansa.dm` | Data Management |
| `ansa.morph` | Morphing operations |

## CLI Command Groups

| Group | Commands | Maps to |
|-------|----------|---------|
| `project` | new, open, save, save-as, info, close | `base.Open`, `base.Save`, `session.New` |
| `mesh` | batch, params, quality, run, stats | `batchmesh.*` |
| `checks` | run, list, report | `base.checks.*` |
| `connections` | read, realize, list | `connections.*` |
| `export` | nastran, lsdyna, abaqus, iges, stl | `base.Output*` |
| `cad` | import, translate, list-parts | `base.Open`, `cad.*` |
| `model` | parts, entities, info | `base.CollectEntities` |
| `session` | status, undo, redo, history | Session state |

## Data Model

- **Native format**: `.ansa` binary files
- **Project state**: JSON session file tracking open model, deck, modifications
- **Solver output**: Nastran (.nas), LS-DYNA (.k), Abaqus (.inp), etc.
- **Intermediate**: IGES, STEP, STL for geometry exchange

## Supported Solver Decks

NASTRAN, LSDYNA, PAMCRASH, ABAQUS, RADIOSS, ANSYS, PERMAS, OPTISTRUCT,
MARC, ACTRAN, IMPETUS, ADVENTURECluster, MOLDEX3D, SESTRA, CFDPP, FLUENT,
OPENFOAM, STAR, UH3D, SCTETRA, TAITHERM, THESEUS, TAU, CGNS
