"""Tests for ProcessRegistry."""

from unittest.mock import MagicMock

import pytest

from app.agents.process_registry import ProcessRegistry


class TestProcessRegistry:
    def test_get_returns_none_for_unknown_key(self):
        registry = ProcessRegistry()
        assert registry.get("unknown") is None

    def test_register_and_get(self):
        registry = ProcessRegistry()
        mock_proc = MagicMock()
        registry.register("p0", mock_proc)
        assert registry.get("p0") is mock_proc

    def test_register_overwrites_existing(self):
        registry = ProcessRegistry()
        mock_proc_1 = MagicMock()
        mock_proc_2 = MagicMock()
        registry.register("p0", mock_proc_1)
        registry.register("p0", mock_proc_2)
        assert registry.get("p0") is mock_proc_2

    def test_shutdown_all_calls_shutdown_on_each(self):
        registry = ProcessRegistry()
        procs = [MagicMock() for _ in range(3)]
        for i, p in enumerate(procs):
            registry.register(f"p{i}", p)
        registry.shutdown_all()
        for p in procs:
            p.shutdown.assert_called_once()

    def test_shutdown_all_clears_registry(self):
        registry = ProcessRegistry()
        registry.register("p0", MagicMock())
        registry.shutdown_all()
        assert registry.get("p0") is None

    def test_shutdown_all_ignores_exceptions(self):
        registry = ProcessRegistry()
        bad_proc = MagicMock()
        bad_proc.shutdown.side_effect = RuntimeError("boom")
        good_proc = MagicMock()
        registry.register("p0", bad_proc)
        registry.register("p1", good_proc)
        registry.shutdown_all()  # should not raise
        good_proc.shutdown.assert_called_once()

    def test_next_id_auto_increments(self):
        registry = ProcessRegistry()
        assert registry.next_id() == "p0"
        assert registry.next_id() == "p1"
        assert registry.next_id() == "p2"
