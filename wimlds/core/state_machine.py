"""
12-stage workflow state machine for the Orchestrator.
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


class Stage(str, Enum):
    VALIDATE           = "validate"
    CREATE_EVENT       = "create_event"
    GENERATE_QR        = "generate_qr"
    CREATE_POSTER      = "create_poster"
    APPROVE_POSTER     = "approve_poster"
    UPLOAD_POSTER      = "upload_poster"
    ANNOUNCE           = "announce"
    SETUP_CONFERENCING = "setup_conferencing"
    SCHEDULE_REMINDERS = "schedule_reminders"
    EVENT_EXECUTION    = "event_execution"
    POST_EVENT         = "post_event"
    ANALYTICS          = "analytics"
    COMPLETED          = "completed"
    FAILED             = "failed"
    HALTED             = "halted"    # Missing fields


# Valid transitions
TRANSITIONS = {
    Stage.VALIDATE:           [Stage.CREATE_EVENT, Stage.HALTED],
    Stage.CREATE_EVENT:       [Stage.GENERATE_QR, Stage.FAILED],
    Stage.GENERATE_QR:        [Stage.CREATE_POSTER, Stage.FAILED],
    Stage.CREATE_POSTER:      [Stage.APPROVE_POSTER, Stage.FAILED],
    Stage.APPROVE_POSTER:     [Stage.UPLOAD_POSTER, Stage.CREATE_POSTER],  # CREATE_POSTER = rework
    Stage.UPLOAD_POSTER:      [Stage.ANNOUNCE, Stage.FAILED],
    Stage.ANNOUNCE:           [Stage.SETUP_CONFERENCING, Stage.FAILED],
    Stage.SETUP_CONFERENCING: [Stage.SCHEDULE_REMINDERS, Stage.FAILED],
    Stage.SCHEDULE_REMINDERS: [Stage.EVENT_EXECUTION, Stage.FAILED],
    Stage.EVENT_EXECUTION:    [Stage.POST_EVENT, Stage.FAILED],
    Stage.POST_EVENT:         [Stage.ANALYTICS, Stage.FAILED],
    Stage.ANALYTICS:          [Stage.COMPLETED],
    Stage.HALTED:             [Stage.VALIDATE],   # Resume after fields filled
    Stage.FAILED:             [],
    Stage.COMPLETED:          [],
}


@dataclass
class WorkflowState:
    event_id: str
    current_stage: Stage = Stage.VALIDATE
    started_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_stages: list[str] = field(default_factory=list)
    error: Optional[str] = None
    retry_count: int = 0
    metadata: dict = field(default_factory=dict)

    def transition(self, new_stage: Stage) -> bool:
        allowed = TRANSITIONS.get(self.current_stage, [])
        if new_stage not in allowed:
            return False
        if self.current_stage != new_stage and self.current_stage.value not in self.completed_stages:
            self.completed_stages.append(self.current_stage.value)
        self.current_stage = new_stage
        self.updated_at = datetime.utcnow()
        return True

    def is_terminal(self) -> bool:
        return self.current_stage in (Stage.COMPLETED, Stage.FAILED)

    def can_resume(self) -> bool:
        return self.current_stage == Stage.HALTED

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "current_stage": self.current_stage.value,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_stages": self.completed_stages,
            "error": self.error,
            "retry_count": self.retry_count,
        }




