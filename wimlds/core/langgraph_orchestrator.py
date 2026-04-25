"""
core/langgraph_orchestrator.py
================================
WiMLDS Pune — LangGraph Multi-Agent Orchestrator

Stages (in order):
  validate → create_event → generate_qr → create_poster → approve_poster
  → upload_poster → announce → setup_conferencing → schedule_reminders
  → event_execution → post_event → analytics → completed

Terminal nodes: completed | failed | halted

Called by the unified CLI via `python run.py langgraph`.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

# ── LangGraph imports ─────────────────────────────────────────────────────────
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise ImportError(
        "langgraph is not installed. Run:  pip install langgraph langchain-core"
    )

from wimlds.core.logger        import get_logger
from wimlds.core.orchestrator  import AgentResult
from wimlds.core.sheets_client import sheets_client

logger = get_logger("langgraph_orchestrator")

MAX_RETRIES = 3

# ── Required fields for pipeline to proceed ────────────────────────────────────
REQUIRED_FIELDS = [
    "event_title", "date", "day", "start_time_ist", "end_time_ist",
    "mode", "speaker_name",
]

# ─────────────────────────────────────────────────────────────────────────────
# State schema
# ─────────────────────────────────────────────────────────────────────────────

class WiMLDSState(TypedDict):
    event_id:           str
    row_num:            int
    dry_run:            bool
    event_data:         dict
    current_node:       str
    completed_stages:   List[str]
    retry_count:        int
    poster_rework_count: int
    last_result:        Optional[dict]
    error:              Optional[str]
    outcome:            str          # "running" | "completed" | "failed" | "halted"
    messages:           List[str]
    audit_log:          List[dict]
    missing_fields:     List[str]
    # Stage outputs written back here
    meetup_url:         Optional[str]
    blog_link:          Optional[str]
    recording_link:     Optional[str]
    halted:             bool


def _initial_state(event_id: str, dry_run: bool) -> WiMLDSState:
    return {
        "event_id":          str(event_id),
        "row_num":           int(event_id),
        "dry_run":           dry_run,
        "event_data":        {},
        "current_node":      "validate",
        "completed_stages":  [],
        "retry_count":       0,
        "poster_rework_count": 0,
        "last_result":       None,
        "error":             None,
        "outcome":           "running",
        "messages":          [],
        "audit_log":         [],
        "missing_fields":    [],
        "meetup_url":        None,
        "blog_link":         None,
        "recording_link":    None,
        "halted":            False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Audit helper
# ─────────────────────────────────────────────────────────────────────────────

def _audit(state: WiMLDSState, stage: str, status: str, detail: str = "") -> list:
    entry = {
        "ts":     datetime.utcnow().isoformat(),
        "stage":  stage,
        "status": status,
        "detail": detail,
    }
    return state.get("audit_log", []) + [entry]


# ─────────────────────────────────────────────────────────────────────────────
# _run_agent — wraps any agent call with retry + state management
# ─────────────────────────────────────────────────────────────────────────────

def _run_agent(
    state:      WiMLDSState,
    node_name:  str,
    agent_fn,           # callable() → AgentResult
) -> WiMLDSState:
    """
    Execute agent_fn(), handle retries, and return updated state.
    """
    try:
        result: AgentResult = agent_fn()
    except Exception as exc:
        logger.error(f"[{node_name}] Uncaught exception: {exc}", exc_info=True)
        return {
            **state,
            "outcome":    "failed",
            "error":      f"{node_name}: {exc}",
            "audit_log":  _audit(state, node_name, "fatal", str(exc)),
        }

    if result.success:
        updated_event = {**state["event_data"], **result.data}
        completed     = list(state["completed_stages"]) + [node_name]
        msg           = f"✓ {node_name}"
        logger.info(msg)
        return {
            **state,
            "event_data":       updated_event,
            "completed_stages": completed,
            "last_result":      {"success": True, "data": result.data},
            "retry_count":      0,
            "messages":         state.get("messages", []) + [msg],
            "audit_log":        _audit(state, node_name, "ok"),
            # Promote key stage outputs to top-level state
            "meetup_url":     result.data.get("meetup_url")   or state.get("meetup_url"),
            "blog_link":      result.data.get("blog_link")    or state.get("blog_link"),
            "recording_link": result.data.get("recording_link") or state.get("recording_link"),
        }
    else:
        # Failure
        retries = state["retry_count"] + 1
        logger.warning(f"[{node_name}] Failed (attempt {retries}): {result.error}")
        new_outcome = "failed" if retries >= MAX_RETRIES else state["outcome"]
        return {
            **state,
            "outcome":     new_outcome,
            "error":       result.error,
            "retry_count": retries,
            "last_result": {"success": False, "error": result.error},
            "audit_log":   _audit(state, node_name, "error", result.error or ""),
        }


# ─────────────────────────────────────────────────────────────────────────────
# NODE IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────────────────

def node_validate(state: WiMLDSState) -> WiMLDSState:
    """Load event data from sheet and validate required fields."""
    try:
        event_data = sheets_client.get_event(state["row_num"])
    except Exception as exc:
        return {
            **state,
            "outcome":   "failed",
            "error":     f"validate: sheet read error — {exc}",
            "audit_log": _audit(state, "validate", "fatal", str(exc)),
        }

    missing = [f for f in REQUIRED_FIELDS if not str(event_data.get(f, "")).strip()]
    if missing:
        logger.warning(f"validate: missing fields — {missing}")
        # Notify organiser (non-fatal if notifier fails)
        try:
            from wimlds.core.notifier import Notifier
            n = Notifier(dry_run=state["dry_run"])
            n.send_missing_fields_alert(
                owner_name  = event_data.get("host_name", "Organiser"),
                owner_email = event_data.get("host_email", ""),
                event_title = event_data.get("event_title", f"Row {state['row_num']}"),
                missing_fields = missing,
            )
        except Exception as e:
            logger.warning(f"Could not send missing-fields alert: {e}")

        return {
            **state,
            "event_data":    event_data,
            "outcome":       "halted",
            "missing_fields": missing,
            "audit_log":     _audit(state, "validate", "halted", str(missing)),
        }

    return {
        **state,
        "event_data":       event_data,
        "outcome":          "running",
        "completed_stages": list(state["completed_stages"]) + ["validate"],
        "audit_log":        _audit(state, "validate", "ok"),
    }


def node_create_event(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.publishing.meetup_agent import MeetupAgent
    agent = MeetupAgent(dry_run=state["dry_run"])
    return _run_agent(state, "create_event",
                      lambda: agent.create_or_update_event(state["event_data"]))


def node_generate_qr(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.publishing.qr_agent import QRAgent
    agent = QRAgent(dry_run=state["dry_run"])
    return _run_agent(state, "generate_qr",
                      lambda: agent.generate_qr(state["event_data"]))


def node_create_poster(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.publishing.poster_agent import PosterAgent
    agent = PosterAgent(dry_run=state["dry_run"])
    return _run_agent(state, "create_poster",
                      lambda: agent.create_poster(state["event_data"]))


def node_approve_poster(state: WiMLDSState) -> WiMLDSState:
    """
    Non-automated stage: read poster_status from the sheet.
    If still 'Pending', self-loop (up to MAX_RETRIES waits).
    """
    try:
        fresh = sheets_client.get_event(state["row_num"])
    except Exception as exc:
        return {**state, "outcome": "failed", "error": str(exc),
                "audit_log": _audit(state, "approve_poster", "fatal", str(exc))}

    status = str(fresh.get("poster_status", "")).strip()
    updated_event = {**state["event_data"], "poster_status": status}

    if status == "Approved":
        return {
            **state,
            "event_data":       updated_event,
            "completed_stages": list(state["completed_stages"]) + ["approve_poster"],
            "audit_log":        _audit(state, "approve_poster", "ok", "Approved"),
        }
    elif status in ("Changes", "Rework"):
        rework = state.get("poster_rework_count", 0) + 1
        return {
            **state,
            "event_data":         updated_event,
            "poster_rework_count": rework,
            "audit_log":          _audit(state, "approve_poster", "rework", status),
        }
    else:
        # Still pending — increment wait counter
        retries = state["retry_count"] + 1
        if retries >= MAX_RETRIES:
            return {**state, "outcome": "failed", "retry_count": retries,
                    "error": "approve_poster: max retries waiting for approval",
                    "audit_log": _audit(state, "approve_poster", "error", "timeout")}
        logger.info(f"approve_poster: status='{status}' — waiting (attempt {retries})")
        return {**state, "retry_count": retries, "event_data": updated_event,
                "audit_log": _audit(state, "approve_poster", "pending", status)}


def node_upload_poster(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.publishing.meetup_agent import MeetupAgent
    agent = MeetupAgent(dry_run=state["dry_run"])
    return _run_agent(state, "upload_poster",
                      lambda: agent.upload_poster(state["event_data"]))


def node_announce(state: WiMLDSState) -> WiMLDSState:
    """
    Multi-channel announcement: Social + WhatsApp groups + Partner outreach.
    WhatsApp failure is non-blocking.
    """
    from wimlds.agents.publishing.social_agent    import SocialAgent
    from wimlds.agents.publishing.whatsapp_agent  import WhatsAppAgent

    social = SocialAgent(dry_run=state["dry_run"])
    wa     = WhatsAppAgent(dry_run=state["dry_run"])

    social_result = social.post_announcement(state["event_data"])
    wa_result     = wa.send_announcement(state["event_data"])

    # Write announce_sent flag
    if not state["dry_run"]:
        try:
            sheets_client.write_field(state["row_num"], "announce_sent", "Y")
        except Exception:
            pass

    # Social failure IS blocking; WA failure is NOT
    if not social_result.success:
        return {
            **state,
            "outcome":   "failed",
            "error":     social_result.error,
            "audit_log": _audit(state, "announce", "error", social_result.error or ""),
        }

    completed = list(state["completed_stages"]) + ["announce"]
    return {
        **state,
        "completed_stages": completed,
        "event_data":       {
            **state["event_data"],
            "announce_sent": "Y",
            **social_result.data,
        },
        "audit_log": _audit(state, "announce", "ok"),
    }


def node_setup_conferencing(state: WiMLDSState) -> WiMLDSState:
    """
    Create Zoom/GMeet/Teams link for Online and Hybrid events.
    For In-Person only: skip (mark as complete).
    """
    mode = state["event_data"].get("mode", "In-Person").strip()
    if mode == "In-Person":
        logger.info("setup_conferencing: In-Person event — skipping")
        return {
            **state,
            "completed_stages": list(state["completed_stages"]) + ["setup_conferencing"],
            "audit_log":        _audit(state, "setup_conferencing", "ok", "skipped (in-person)"),
        }

    # Try Zoom first, fall back to GMeet
    if _has_zoom_creds():
        from wimlds.integrations.meeting.zoom_client import zoom_client
        return _run_agent(
            state, "setup_conferencing",
            lambda: _create_zoom_meeting(zoom_client, state["event_data"])
        )
    else:
        from wimlds.integrations.meeting.gmeet_client import gmeet_client
        return _run_agent(
            state, "setup_conferencing",
            lambda: _create_gmeet(gmeet_client, state["event_data"])
        )


def node_schedule_reminders(state: WiMLDSState) -> WiMLDSState:
    """
    Schedule T-2d, T-1d, T-2h reminders.
    In the simplified version these are sent immediately via social/WA;
    a real production scheduler would use APScheduler or Cloud Tasks.
    """
    if state["dry_run"]:
        logger.info("[DRY-RUN] Would schedule reminder blasts")
        return {
            **state,
            "completed_stages": list(state["completed_stages"]) + ["schedule_reminders"],
            "audit_log":        _audit(state, "schedule_reminders", "ok", "dry-run"),
        }

    # For now: no-op placeholder (real deployment uses a scheduler)
    logger.info("schedule_reminders: queued (implement scheduler in production)")
    return {
        **state,
        "completed_stages": list(state["completed_stages"]) + ["schedule_reminders"],
        "audit_log":        _audit(state, "schedule_reminders", "ok"),
    }


def node_event_execution(state: WiMLDSState) -> WiMLDSState:
    """
    Day-of-event stage: send T-2h bump and stand by.
    Marks event_status = 'In Progress'.
    """
    from wimlds.agents.publishing.social_agent   import SocialAgent
    from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent

    social = SocialAgent(dry_run=state["dry_run"])
    wa     = WhatsAppAgent(dry_run=state["dry_run"])

    social.post_final_bump(state["event_data"])
    wa.send_final_bump(state["event_data"])

    if not state["dry_run"]:
        try:
            sheets_client.write_field(state["row_num"], "event_status", "In Progress")
        except Exception:
            pass

    return {
        **state,
        "completed_stages": list(state["completed_stages"]) + ["event_execution"],
        "event_data":       {**state["event_data"], "event_status": "In Progress"},
        "audit_log":        _audit(state, "event_execution", "ok"),
    }


def node_post_event(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.post_event.post_event_agent import PostEventAgent
    agent = PostEventAgent(dry_run=state["dry_run"])

    def _run():
        result = agent.run(
            event_data      = state["event_data"],
            meeting_id      = state["event_data"].get("_meeting_id"),
            platform        = state["event_data"].get("_platform", "zoom"),
            transcript_path = state["event_data"].get("_transcript_path"),
        )
        return AgentResult(
            success = result.success,
            data    = result.data,
            error   = "; ".join(result.errors) if result.errors else None,
        )

    return _run_agent(state, "post_event", _run)


def node_analytics(state: WiMLDSState) -> WiMLDSState:
    from wimlds.agents.post_event.analytics_agent import AnalyticsAgent
    agent = AnalyticsAgent(dry_run=state["dry_run"])
    return _run_agent(
        state, "analytics",
        lambda: agent.run(state["event_data"], state["row_num"])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Terminal nodes
# ─────────────────────────────────────────────────────────────────────────────

def node_completed(state: WiMLDSState) -> WiMLDSState:
    logger.info("Pipeline COMPLETED ✅")
    return {**state, "outcome": "completed"}


def node_failed(state: WiMLDSState) -> WiMLDSState:
    logger.error(f"Pipeline FAILED ❌ — {state.get('error', 'unknown error')}")
    return {**state, "outcome": "failed"}


def node_halted(state: WiMLDSState) -> WiMLDSState:
    logger.warning(f"Pipeline HALTED ⏸  — missing: {state.get('missing_fields', [])}")
    return {**state, "outcome": "halted", "halted": True}


# ─────────────────────────────────────────────────────────────────────────────
# Routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_validate(state: WiMLDSState) -> str:
    o = state["outcome"]
    if o == "halted":  return "halted"
    if o == "failed":  return "failed"
    return "create_event"


def route_after_create_event(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "generate_qr"


def route_after_generate_qr(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "create_poster"


def route_after_create_poster(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "approve_poster"


def route_after_approve_poster(state: WiMLDSState) -> str:
    if state["outcome"] == "failed":
        return "failed"
    status = state["event_data"].get("poster_status", "").strip()
    if status == "Approved":
        return "upload_poster"
    if status in ("Changes", "Rework"):
        return "create_poster"
    # Pending — check retry limit
    if state["retry_count"] >= MAX_RETRIES:
        return "failed"
    return "approve_poster"   # self-loop


def route_after_upload_poster(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "announce"


def route_after_announce(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "setup_conferencing"


def route_after_setup_conferencing(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "schedule_reminders"


def route_after_schedule_reminders(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "event_execution"


def route_after_event_execution(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "post_event"


def route_after_post_event(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "analytics"


def route_after_analytics(state: WiMLDSState) -> str:
    return "failed" if state["outcome"] == "failed" else "completed"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(WiMLDSState)

    # Nodes
    for name, fn in [
        ("validate",           node_validate),
        ("create_event",       node_create_event),
        ("generate_qr",        node_generate_qr),
        ("create_poster",      node_create_poster),
        ("approve_poster",     node_approve_poster),
        ("upload_poster",      node_upload_poster),
        ("announce",           node_announce),
        ("setup_conferencing", node_setup_conferencing),
        ("schedule_reminders", node_schedule_reminders),
        ("event_execution",    node_event_execution),
        ("post_event",         node_post_event),
        ("analytics",          node_analytics),
        ("completed",          node_completed),
        ("failed",             node_failed),
        ("halted",             node_halted),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("validate")

    # Edges with conditional routing
    g.add_conditional_edges("validate",           route_after_validate,           {
        "create_event": "create_event", "halted": "halted", "failed": "failed"
    })
    g.add_conditional_edges("create_event",       route_after_create_event,       {
        "generate_qr": "generate_qr", "failed": "failed"
    })
    g.add_conditional_edges("generate_qr",        route_after_generate_qr,        {
        "create_poster": "create_poster", "failed": "failed"
    })
    g.add_conditional_edges("create_poster",      route_after_create_poster,      {
        "approve_poster": "approve_poster", "failed": "failed"
    })
    g.add_conditional_edges("approve_poster",     route_after_approve_poster,     {
        "upload_poster": "upload_poster",
        "create_poster": "create_poster",
        "approve_poster": "approve_poster",
        "failed": "failed",
    })
    g.add_conditional_edges("upload_poster",      route_after_upload_poster,      {
        "announce": "announce", "failed": "failed"
    })
    g.add_conditional_edges("announce",           route_after_announce,           {
        "setup_conferencing": "setup_conferencing", "failed": "failed"
    })
    g.add_conditional_edges("setup_conferencing", route_after_setup_conferencing, {
        "schedule_reminders": "schedule_reminders", "failed": "failed"
    })
    g.add_conditional_edges("schedule_reminders", route_after_schedule_reminders, {
        "event_execution": "event_execution", "failed": "failed"
    })
    g.add_conditional_edges("event_execution",    route_after_event_execution,    {
        "post_event": "post_event", "failed": "failed"
    })
    g.add_conditional_edges("post_event",         route_after_post_event,         {
        "analytics": "analytics", "failed": "failed"
    })
    g.add_conditional_edges("analytics",          route_after_analytics,          {
        "completed": "completed", "failed": "failed"
    })

    g.add_edge("completed", END)
    g.add_edge("failed",    END)
    g.add_edge("halted",    END)

    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Public API used by the unified LangGraph CLI command
# ─────────────────────────────────────────────────────────────────────────────

def run_full_pipeline(
    event_id:   str,
    dry_run:    bool = False,
    resume:     bool = False,
    from_stage: str  = None,
) -> WiMLDSState:
    """
    Run the complete LangGraph pipeline for one event.
    Returns the final state dict.
    """
    graph = build_graph()
    state = _initial_state(event_id, dry_run)

    if from_stage:
        # Pre-populate completed stages so routing skips earlier nodes
        STAGE_ORDER = [
            "validate", "create_event", "generate_qr", "create_poster",
            "approve_poster", "upload_poster", "announce", "setup_conferencing",
            "schedule_reminders", "event_execution", "post_event", "analytics",
        ]
        idx = STAGE_ORDER.index(from_stage) if from_stage in STAGE_ORDER else 0
        state["completed_stages"] = STAGE_ORDER[:idx]
        # Still need to load event data
        try:
            state["event_data"] = sheets_client.get_event(int(event_id))
        except Exception as e:
            logger.warning(f"Could not pre-load event data for --from-stage: {e}")

    logger.info(f"Pipeline starting — event {event_id}, dry_run={dry_run}")
    final = graph.invoke(state)
    return final


def run_single_agent(
    event_id:   str,
    agent_name: str,
    dry_run:    bool = False,
) -> dict:
    """
    Run a single agent node in isolation (no graph routing).
    Returns a minimal result dict.
    """
    NODE_MAP = {
        "validate":           node_validate,
        "create_event":       node_create_event,
        "generate_qr":        node_generate_qr,
        "create_poster":      node_create_poster,
        "approve_poster":     node_approve_poster,
        "upload_poster":      node_upload_poster,
        "announce":           node_announce,
        "setup_conferencing": node_setup_conferencing,
        "schedule_reminders": node_schedule_reminders,
        "event_execution":    node_event_execution,
        "post_event":         node_post_event,
        "analytics":          node_analytics,
    }
    node_fn = NODE_MAP.get(agent_name)
    if not node_fn:
        return {"success": False, "error": f"Unknown agent: {agent_name}"}

    state = _initial_state(event_id, dry_run)
    try:
        state["event_data"] = sheets_client.get_event(int(event_id))
    except Exception as e:
        state["event_data"] = {}
        logger.warning(f"Could not load event data: {e}")

    final = node_fn(state)
    return {
        "success":    final.get("outcome") not in ("failed",),
        "error":      final.get("error"),
        "next_node":  final.get("current_node"),
        "audit_log":  final.get("audit_log", []),
        "event_data": final.get("event_data", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LangGraphOrchestrator class (used by tests)
# ─────────────────────────────────────────────────────────────────────────────

class LangGraphOrchestrator:
    """Thin class wrapper for test compatibility and optional OOP use."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def get_status(self, event_id: str = None) -> list:
        if event_id:
            data = sheets_client.get_event(int(event_id))
            return [{"id": str(event_id), **data}]
        all_events = sheets_client.get_all_upcoming()
        return [{"id": str(e.get("_row_number", "?")), **e} for e in all_events]

    def run_agent(self, event_id: str, agent_name: str) -> dict:
        """Run a single named agent. Returns {success, error, ...}."""
        NODE_MAP = {
            "validate":           node_validate,
            "create_event":       node_create_event,
            "generate_qr":        node_generate_qr,
            "create_poster":      node_create_poster,
            "approve_poster":     node_approve_poster,
            "upload_poster":      node_upload_poster,
            "announce":           node_announce,
            "setup_conferencing": node_setup_conferencing,
            "schedule_reminders": node_schedule_reminders,
            "event_execution":    node_event_execution,
            "post_event":         node_post_event,
            "analytics":          node_analytics,
        }
        if agent_name not in NODE_MAP:
            return {"success": False, "error": f"Unknown agent node: {agent_name}"}

        state = _initial_state(event_id, self.dry_run)
        state["event_data"] = sheets_client.get_event(int(event_id))
        final = NODE_MAP[agent_name](state)
        return {
            "success":  final.get("outcome") != "failed",
            "error":    final.get("error"),
            "data":     final.get("event_data", {}),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Conferencing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_zoom_creds() -> bool:
    try:
        from wimlds.config.settings import settings
        return bool(settings.zoom_account_id and settings.zoom_client_id)
    except Exception:
        return False


def _create_zoom_meeting(zoom_client, event_data: dict) -> AgentResult:
    try:
        meeting = zoom_client.create_meeting(event_data)
        return AgentResult(success=True, data={
            "conference_link": meeting.join_url,
            "_meeting_id":     meeting.meeting_id,
            "_platform":       "zoom",
        })
    except Exception as exc:
        return AgentResult(success=False, error=str(exc))


def _create_gmeet(gmeet_client, event_data: dict) -> AgentResult:
    try:
        result = gmeet_client.create_meeting(event_data)
        return AgentResult(success=True, data={
            "conference_link": result.get("hangoutLink", ""),
            "_meeting_id":     result.get("id", ""),
            "_platform":       "gmeet",
        })
    except Exception as exc:
        return AgentResult(success=False, error=str(exc))



