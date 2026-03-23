# ANSA CLI Harness — Test Plan & Results

## Test Inventory

- `test_core.py`: ~40 unit tests (synthetic data, no ANSA dependency)
- `test_full_e2e.py`: ~15 E2E tests (requires running ANSA instance)

## Unit Test Plan (`test_core.py`)

### Project Module (`project.py`)
- `test_create_project_default` — default deck, metadata fields
- `test_create_project_with_deck` — each solver deck
- `test_create_project_invalid_deck` — error handling
- `test_create_project_with_output` — JSON file creation
- `test_load_project` — load from saved JSON
- `test_save_project` — save and reload roundtrip
- **Expected: 8 tests**

### Session Module (`session.py`)
- `test_session_create` — empty session
- `test_session_record` — action recording
- `test_session_undo_redo` — undo/redo stack
- `test_session_save_load` — persistence roundtrip
- `test_session_status` — status dict structure
- `test_session_history` — history list
- **Expected: 8 tests**

### Export Module (`export.py`)
- `test_list_export_formats` — format listing
- `test_export_solver_invalid_format` — error for unknown format
- `test_export_geometry_invalid_format` — error for unknown format
- **Expected: 3 tests**

### Checks Module (`checks.py`)
- `test_list_check_types` — check types listing
- **Expected: 1 test**

### Connections Module (`connections.py`)
- Tested via E2E only (requires ANSA backend)

### Backend Module (`ansa_backend.py`)
- `test_iap_message_header_pack_unpack` — header serialization
- `test_iap_ie_pack_int` — integer IE packing
- `test_iap_ie_pack_string` — string IE packing
- `test_build_script` — script builder helper
- `test_find_ansa_missing` — error when ANSA not found
- `test_free_port` — port allocation
- **Expected: 8 tests**

### CLI Module (`ansa_cli.py`)
- `test_cli_help` — help output
- `test_cli_project_new` — project new command
- `test_cli_export_formats` — format listing command
- `test_cli_checks_list` — check types listing
- **Expected: 6 tests**

### Subprocess Tests (`TestCLISubprocess`)
- `test_help` — --help flag
- `test_project_new_json` — project new with JSON output
- `test_export_formats_json` — export formats JSON
- `test_checks_list_json` — checks list JSON
- **Expected: 6 tests**

**Total planned: ~40 unit tests**

## E2E Test Plan (`test_full_e2e.py`)

### Prerequisites
- ANSA v22+ installed and `ANSA_HOME` set
- Test model files in test fixtures directory

### Workflows
1. **Basic Project Workflow**: new → open model → info → save → export Nastran
2. **Batch Mesh Workflow**: open → create session → load params → run → stats
3. **Quality Check Workflow**: open → run mesh checks → run geometry checks
4. **Connections Workflow**: open → read connections → realize → list
5. **Multi-format Export**: open → export Nastran, IGES, STL

### Verification
- Exported files exist and size > 0
- Nastran output contains GRID/CQUAD4 cards
- IGES output has valid header
- JSON output from --json flag is parseable

## Test Results

Last run: 2026-03-21

```
cli_anything\ansa\tests\test_core.py::TestProject::test_create_project_default PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_create_project_with_deck PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_create_project_invalid_deck PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_create_project_with_output PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_load_project PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_save_project PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_save_project_no_path PASSED
cli_anything\ansa\tests\test_core.py::TestProject::test_decks_completeness PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_create PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_record PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_undo_redo PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_undo_empty PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_redo_empty PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_save_load PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_status PASSED
cli_anything\ansa\tests\test_core.py::TestSession::test_session_redo_cleared_on_new_action PASSED
cli_anything\ansa\tests\test_core.py::TestExport::test_list_export_formats PASSED
cli_anything\ansa\tests\test_core.py::TestExport::test_export_solver_invalid PASSED
cli_anything\ansa\tests\test_core.py::TestExport::test_export_geometry_invalid PASSED
cli_anything\ansa\tests\test_core.py::TestChecks::test_list_check_types PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_message_header_pack_unpack PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_ie_pack_int PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_ie_pack_string PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_build_script PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_build_script_custom_imports PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_free_port PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_find_ansa_not_installed PASSED
cli_anything\ansa\tests\test_core.py::TestBackend::test_calculate_padding PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_help PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_project_new PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_project_new_json PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_export_formats PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_checks_list PASSED
cli_anything\ansa\tests\test_core.py::TestCLI::test_cli_session_status PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_help PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_project_new_json PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_export_formats_json PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_checks_list_json PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_session_status_json PASSED
cli_anything\ansa\tests\test_core.py::TestCLISubprocess::test_project_new_and_reload PASSED

============================= 40 passed in 0.90s ==============================
```

**Summary**: 40 passed, 0 failed in 0.90s

### Coverage Notes
- Unit tests cover all core modules without ANSA dependency
- Subprocess tests verify the installed `cli-anything-ansa` command works
- E2E tests (`test_full_e2e.py`) require ANSA_HOME to be set and ANSA installed
- E2E tests were skipped in this run (ANSA not available in test environment)
