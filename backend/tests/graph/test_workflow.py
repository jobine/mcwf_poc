"""Tests for workflow integration with ProcessRegistry."""

from unittest.mock import MagicMock, patch

from app.agents.process_registry import ProcessRegistry


class TestWorkflowRegistry:
    """Verify that create_ansa_workflow passes a registry to agents and deinit."""

    @patch("app.graph.workflow._load_graph_config")
    def test_agents_receive_shared_registry(self, mock_config):
        mock_config.return_value = {
            "agents": [
                {"name": "classifier", "type": "AnsaAgent", "model_path": "m.ansa", "script_path": "s.py"},
                {"name": "cleaner", "type": "AnsaAgent", "script_path": "c.py"},
            ]
        }

        from app.graph.workflow import create_classifier_node, create_cleaner_node

        registry = ProcessRegistry()
        classifier = create_classifier_node(registry=registry)
        cleaner = create_cleaner_node(registry=registry)

        assert classifier._registry is registry
        assert cleaner._registry is registry


class TestDeinitShutdownsRegistry:
    """Verify deinit_experiment calls registry.shutdown_all()."""

    def test_deinit_shuts_down_registry(self, tmp_path, monkeypatch):
        from app.graph.workflow import deinit_experiment
        from app.config import settings

        monkeypatch.setattr(settings, "experiments_dir", tmp_path)

        registry = ProcessRegistry()
        mock_proc = MagicMock()
        registry.register("p0", mock_proc)

        deinit_fn = deinit_experiment(on_event=None, registry=registry)
        deinit_fn({
            "experiment_id": "test-exp",
            "status": "success",
            "result": None,
            "error": None,
            "stdout_lines": [],
            "stderr_lines": [],
        })

        mock_proc.shutdown.assert_called_once()
