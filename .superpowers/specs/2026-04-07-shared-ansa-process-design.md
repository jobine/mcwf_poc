# Shared AnsaProcess Design Spec

## Problem

Each `AnsaAgent` currently starts its own `AnsaProcess` in `execute()`. When agents need to operate on the same in-memory model (e.g., classifier loads a model, cleaner cleans it), they must share the same ANSA process. Otherwise the cleaner operates on an empty database.

## Solution

Introduce a **workflow-level `ProcessRegistry`** that holds live `AnsaProcess` instances, keyed by a simple `process_id` string. Agents create or reuse processes based on whether `process_id` already exists in the LangGraph state.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sharing mechanism | Workflow-level registry (dict) | AnsaProcess is not serializable; registry lives outside state |
| Registry key | Simple `process_id` string | Decoupled from model_path; flexible for future use |
| Create vs reuse | Based on `process_id` presence in state | Not based on `model_path`; allows reuse even when opening a new model |
| Open model | Based on `model_path` presence in agent config | Independent of create/reuse decision |
| Lifecycle | First user creates; `deinit_experiment` shuts down all | No explicit start/stop nodes needed |

## Detailed Design

### 1. ProcessRegistry

A simple class in `ansa_agent.py` (or a new small module):

```python
class ProcessRegistry:
    """Holds live AnsaProcess instances, keyed by process_id."""

    def __init__(self):
        self._processes: dict[str, AnsaProcess] = {}

    def get(self, process_id: str) -> AnsaProcess | None:
        return self._processes.get(process_id)

    def register(self, process_id: str, process: AnsaProcess) -> None:
        self._processes[process_id] = process

    def shutdown_all(self) -> None:
        for proc in self._processes.values():
            try:
                proc.shutdown()
            except Exception:
                pass
        self._processes.clear()
```

### 2. AnsaAgentState (state.py)

Add one field:

```python
class AnsaAgentState(TypedDict, total=False):
    # ... existing fields ...
    process_id: str | None  # key into ProcessRegistry
```

### 3. AnsaAgent (ansa_agent.py)

Changes to `__init__`:
- Accept `registry: ProcessRegistry` parameter.

Changes to `execute()`:

```
if state has process_id AND registry has that process:
    backend = registry.get(process_id)
else:
    backend = AnsaProcess()  # start new
    process_id = generate short id
    registry.register(process_id, backend)
    backend.connect()
    backend.start_output_reader(on_stdout, on_stderr)

if self._model_path:
    open_model(backend, model_path)

run_script(backend, script)

return {... "process_id": process_id}
```

Key changes from current code:
- No more `with AnsaProcess() as backend:` context manager (process outlives the agent)
- Output readers are started once by the creating agent; reusing agents attach their own callbacks or share the existing ones
- Process is NOT shut down at the end of execute()

### 4. Workflow (workflow.py)

```python
def create_ansa_workflow(on_event=None):
    registry = ProcessRegistry()

    classifier_node = create_classifier_node(on_event, registry)
    cleaner_node = create_cleaner_node(on_event, registry)

    # ... build graph as before ...

    # deinit_experiment receives registry to clean up
    graph.add_node("deinit_workflow", deinit_experiment(on_event, registry))
```

### 5. deinit_experiment (workflow.py)

Add `registry` parameter. After persisting results, call `registry.shutdown_all()`.

### 6. graph.json

No changes needed. The cleaner already has no `model_path`.

## Agent Execution Flow

```
classifier.execute(state={})
  -> no process_id in state
  -> create AnsaProcess, register as "p0"
  -> open_model (has model_path)
  -> run_script
  -> return {process_id: "p0", ...}

cleaner.execute(state={process_id: "p0"})
  -> process_id "p0" found in registry
  -> reuse existing process
  -> skip open_model (no model_path)
  -> run_script
  -> return {process_id: "p0", ...}

deinit_experiment(state)
  -> persist results
  -> registry.shutdown_all()  # shuts down "p0"
```

## Output Reader Handling

When reusing a process, the stdout/stderr reader threads are already running from the first agent. The reusing agent needs to either:
- **Option: Swap callbacks** — replace the on_stdout/on_stderr callbacks so events are emitted with the correct agent name. This requires making the callbacks settable on AnsaProcess.

This detail can be resolved during implementation. The simplest approach is to make the output callbacks replaceable on AnsaProcess.

## Error Handling

- If an agent fails, `process_id` is still returned in state so subsequent agents (or deinit) can still access and clean up the process.
- `registry.shutdown_all()` in deinit is a safety net — always runs regardless of workflow success/failure.
- If `process_id` is in state but not in registry (e.g., process crashed), the agent should treat it as "no process" and create a new one or error out.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/graph/state.py` | Add `process_id` field |
| `backend/app/agents/ansa_agent.py` | Add `ProcessRegistry` class; refactor `execute()` to create/reuse |
| `backend/app/graph/workflow.py` | Create registry, pass to agents and deinit |
