"""Tests for AnsaAgentState type definition."""

from app.graph.state import AnsaAgentState


class TestAnsaAgentState:
    def test_process_id_field_accepted(self):
        """process_id should be an accepted optional field."""
        state: AnsaAgentState = {
            "experiment_id": "abc",
            "status": "pending",
            "process_id": "p0",
        }
        assert state["process_id"] == "p0"

    def test_process_id_defaults_absent(self):
        """State without process_id should still be valid (total=False)."""
        state: AnsaAgentState = {
            "experiment_id": "abc",
            "status": "pending",
        }
        assert "process_id" not in state
