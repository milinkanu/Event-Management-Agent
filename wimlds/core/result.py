"""AgentResult dataclass — mirrors main codebase orchestrator."""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AgentResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None


