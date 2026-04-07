"""Tests for AnsaAgent with ProcessRegistry support."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.ansa_agent import AnsaAgent
from app.agents.process_registry import ProcessRegistry


def _make_agent(name="test_agent", model_path=None, script_path=None, registry=None, on_event=None):
    """Helper to build an AnsaAgent with mocked paths."""
    return AnsaAgent(
        name=name,
        model_path=model_path,
        script_path=script_path,
        registry=registry,
        on_event=on_event,
    )


class TestAnsaAgentCreatesProcess:
    """When no process_id in state, agent creates a new AnsaProcess."""

    @patch("app.agents.ansa_agent.open_model")
    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_creates_process_and_registers(self, MockProcess, mock_open_model):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}
        mock_open_model.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(
            model_path=model_path,
            script_path=script_path,
            registry=registry,
        )
        result = agent.execute({"status": "pending"})

        # Process was created and registered
        assert result["process_id"] is not None
        assert registry.get(result["process_id"]) is mock_backend
        # Process was connected and output readers started
        mock_backend.connect.assert_called_once()
        mock_backend.start_output_reader.assert_called_once()
        # Model was opened
        mock_open_model.assert_called_once()

    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_creates_process_without_model_path(self, MockProcess):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending"})

        assert result["process_id"] is not None
        assert result["status"] == "success"


class TestAnsaAgentReusesProcess:
    """When process_id exists in state and registry, agent reuses it."""

    def test_reuses_existing_process(self):
        mock_backend = MagicMock()
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        registry.register("p0", mock_backend)

        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending", "process_id": "p0"})

        assert result["process_id"] == "p0"
        assert result["status"] == "success"
        # Should NOT have created a new process
        mock_backend.run_script.assert_called_once()

    @patch("app.agents.ansa_agent.open_model")
    def test_reuses_process_and_opens_model(self, mock_open_model):
        mock_backend = MagicMock()
        mock_backend.run_script.return_value = {"success": True}
        mock_open_model.return_value = {"success": True}

        registry = ProcessRegistry()
        registry.register("p0", mock_backend)

        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(
            model_path=model_path,
            script_path=script_path,
            registry=registry,
        )
        result = agent.execute({"status": "pending", "process_id": "p0"})

        assert result["process_id"] == "p0"
        mock_open_model.assert_called_once()


class TestAnsaAgentErrorHandling:
    def test_missing_script_file(self):
        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = False
        model_path = MagicMock(spec=Path)
        model_path.is_file.return_value = True

        agent = _make_agent(model_path=model_path, script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending"})
        assert result["status"] == "error"
        assert "process_id" in result

    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_process_id_in_state_but_not_in_registry(self, MockProcess):
        """If process_id references a dead process, create a new one."""
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(script_path=script_path, registry=registry)
        result = agent.execute({"status": "pending", "process_id": "dead_id"})

        # Should create a new process since "dead_id" is not in registry
        assert result["process_id"] != "dead_id"
        assert result["status"] == "success"


class TestAnsaAgentEvents:
    @patch("app.agents.ansa_agent.AnsaProcess")
    def test_emits_lifecycle_events(self, MockProcess):
        mock_backend = MagicMock()
        MockProcess.return_value = mock_backend
        mock_backend.run_script.return_value = {"success": True}

        events = []
        registry = ProcessRegistry()
        script_path = MagicMock(spec=Path)
        script_path.is_file.return_value = True

        agent = _make_agent(
            script_path=script_path,
            registry=registry,
            on_event=events.append,
        )
        agent.execute({"status": "pending"})

        event_types = [e["type"] for e in events]
        assert "agent_started" in event_types
        assert "agent_completed" in event_types
