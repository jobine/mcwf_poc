"""Session management — state persistence, undo/redo tracking."""

import json
import os
import time


class Session:
    """Manages CLI session state for ANSA operations."""

    def __init__(self, session_path=None):
        self.session_path = session_path
        self.project = None
        self._history = []
        self._undo_stack = []
        self._redo_stack = []

        if session_path and os.path.exists(session_path):
            self.load(session_path)

    def load(self, path):
        """Load session state from file."""
        with open(path, "r") as f:
            data = json.load(f)
        self.project = data.get("project")
        self._history = data.get("history", [])
        self.session_path = path
        return self

    def save(self, path=None):
        """Save session state to file."""
        path = path or self.session_path
        if not path:
            raise ValueError("No session path specified")

        data = {
            "project": self.project,
            "history": self._history,
            "saved": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.session_path = path
        return self

    def record(self, action, details=None):
        """Record an action in the session history."""
        entry = {
            "action": action,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if details:
            entry["details"] = details
        self._history.append(entry)
        self._undo_stack.append(entry)
        self._redo_stack.clear()

    def undo_last(self):
        """Pop the last action from undo stack."""
        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        self._redo_stack.append(entry)
        return entry

    def redo_last(self):
        """Re-apply the last undone action."""
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        self._undo_stack.append(entry)
        return entry

    @property
    def history(self):
        return list(self._history)

    def status(self):
        """Get current session status."""
        return {
            "session_path": self.session_path,
            "project": self.project.get("name") if self.project else None,
            "model_path": self.project.get("model_path") if self.project else None,
            "history_count": len(self._history),
            "undo_available": len(self._undo_stack),
            "redo_available": len(self._redo_stack),
        }
