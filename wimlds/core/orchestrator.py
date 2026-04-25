"""
core/orchestrator.py
====================
Shared AgentResult dataclass and base orchestrator utilities.
All agents import AgentResult from here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class AgentResult:
    """Standardised return value from every agent method."""
    success: bool
    data:    dict          = field(default_factory=dict)
    error:   Optional[str] = None

    def merge_into(self, state: dict) -> None:
        """Shallow-merge result.data into a LangGraph state dict."""
        if self.data:
            state.update(self.data)


