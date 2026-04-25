#!/usr/bin/env python3
"""Unified CLI for the WiMLDS meetup automation project."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from wimlds.core.logger import get_logger

logger = get_logger("cli")
load_dotenv("wimlds/config/.env")

VALID_LG_STAGES = [
    "validate", "create_event", "generate_qr", "create_poster",
    "approve_poster", "upload_poster", "announce", "setup_conferencing",
    "schedule_reminders", "event_execution", "post_event", "analytics",
]
VALID_SOCIAL_STAGES = ["announcement", "spotlight", "logistics", "final_bump"]
VALID_SOCIAL_CHANNELS = ["all", "linkedin", "twitter", "facebook", "instagram", "whatsapp", "meetup"]


def _classic_orchestrator():
    try:
        from wimlds.core.orchestrator import Orchestrator
        return Orchestrator
    except Exception:
        return None


def _langgraph_api():
    from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator, run_full_pipeline, run_single_agent
    return LangGraphOrchestrator, run_full_pipeline, run_single_agent


def _sheets_client():
    from wimlds.core.sheets_client import sheets_client
    return sheets_client


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """WiMLDS Pune Meetup Automation System CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("event")
@click.option("--event-id", required=True, help="Master Sheet row ID (e.g. row number or event slug)")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without making real API calls")
@click.option("--agent", default=None, help="Run only a specific agent")
@click.option("--stage", default=None, help="Optional stage or starting stage")
@click.option("--resume", is_flag=True, default=False, help="Resume from last successful stage")
def event_command(event_id, dry_run, agent, stage, resume):
    """Trigger the main automation workflow for a single event."""
    if dry_run:
        click.secho("DRY-RUN MODE: no real API calls will be made", fg="yellow", bold=True)

    click.secho(f"\nStarting automation for event: {event_id}", fg="cyan", bold=True)
    Orchestrator = _classic_orchestrator()
    if Orchestrator is not None:
        orchestrator = Orchestrator(dry_run=dry_run)
        if agent:
            result = orchestrator.run_agent(event_id=event_id, agent_name=agent, stage=stage)
        else:
            result = orchestrator.run_pipeline(event_id=event_id, resume=resume)
        if result.success:
            click.secho("\nCompleted successfully", fg="green", bold=True)
            for msg in result.messages:
                click.echo(f"   {msg}")
            return
        click.secho(f"\nPipeline failed at stage: {result.failed_stage}", fg="red", bold=True)
        click.echo(f"   Error: {result.error}")
        sys.exit(1)

    _, run_full_pipeline, run_single_agent = _langgraph_api()
    if agent:
        result = run_single_agent(event_id=event_id, agent_name=agent, dry_run=dry_run)
        if result.get("success"):
            click.secho("\nCompleted successfully", fg="green", bold=True)
            return
        click.secho(f"\nAgent failed: {result.get('error')}", fg="red", bold=True)
        sys.exit(1)

    result = run_full_pipeline(event_id=event_id, dry_run=dry_run, resume=resume, from_stage=stage)
    if result.get("error"):
        click.secho(f"\nPipeline failed: {result.get('error')}", fg="red", bold=True)
        sys.exit(1)
    if result.get("halted"):
        click.secho("\nPipeline halted - missing fields detected", fg="yellow", bold=True)
        for field in result.get("missing_fields", []):
            click.echo(f"  - {field}")
        return
    click.secho("\nCompleted successfully", fg="green", bold=True)


@cli.command("status")
@click.option("--event-id", default=None, help="Check specific event (omit for all pending)")
def status_command(event_id):
    """Show status of pending or active events."""
    Orchestrator = _classic_orchestrator()
    if Orchestrator is not None:
        events = Orchestrator().get_status(event_id=event_id)
    else:
        LangGraphOrchestrator, _, _ = _langgraph_api()
        events = LangGraphOrchestrator().get_status(event_id=event_id)

    if not events:
        click.echo("No active events found.")
        return

    click.secho(f"\n{'EVENT ID':<20} {'TITLE':<35} {'STATUS':<12}", bold=True)
    click.echo("-" * 75)
    for ev in events:
        status = ev.get("status", ev.get("event_status", "?"))
        color = "green" if status == "Completed" else "yellow" if status == "Upcoming" else "red"
        click.secho(f"{ev.get('id', '?'):<20} {ev.get('title', ev.get('event_title', '?'))[:34]:<35} {status:<12}", fg=color)


@cli.command("validate")
@click.option("--event-id", default=None, help="Validate a specific event row")
@click.option("--config", is_flag=True, default=False, help="Validate system configuration and credentials")
def validate_command(event_id, config):
    """Validate configuration and or event data."""
    if config:
        click.echo("Validating system configuration...")
        from wimlds.scripts.validate_config import validate_all
        errors = validate_all()
        if errors:
            for error in errors:
                click.secho(f"  x {error}", fg="red")
            sys.exit(1)
        click.secho("  OK: all configuration checks passed", fg="green")

    if event_id:
        Orchestrator = _classic_orchestrator()
        if Orchestrator is not None and hasattr(Orchestrator(), "validate_event"):
            result = Orchestrator().validate_event(event_id=event_id)
            if result.valid:
                click.secho(f"  OK: event {event_id} has all required fields", fg="green")
            else:
                click.secho(f"  Missing fields for event {event_id}:", fg="red")
                for field in result.missing_fields:
                    click.echo(f"      - {field}")
            return

        _, _, run_single_agent = _langgraph_api()
        result = run_single_agent(event_id=event_id, agent_name="validate", dry_run=False)
        if result.get("success"):
            click.secho(f"  OK: event {event_id} validation passed", fg="green")
        else:
            click.secho(f"  Validation issue for event {event_id}: {result.get('error')}", fg="red")


@cli.command("post-event")
@click.option("--event-id", required=True)
@click.option("--dry-run", is_flag=True, default=False)
def post_event_pipeline_command(event_id, dry_run):
    """Run the post-event pipeline through the available orchestrator."""
    Orchestrator = _classic_orchestrator()
    if Orchestrator is not None:
        result = Orchestrator(dry_run=dry_run).run_agent(event_id=event_id, agent_name="post_event")
        if result.success:
            click.secho("Post-event pipeline complete", fg="green")
            return
        click.secho(f"Failed: {result.error}", fg="red")
        sys.exit(1)

    _, _, run_single_agent = _langgraph_api()
    result = run_single_agent(event_id=event_id, agent_name="post_event", dry_run=dry_run)
    if result.get("success"):
        click.secho("Post-event pipeline complete", fg="green")
    else:
        click.secho(f"Failed: {result.get('error')}", fg="red")
        sys.exit(1)


@cli.command("scheduler")
@click.option("--start", is_flag=True, help="Start the background reminder scheduler")
@click.option("--stop", is_flag=True, help="Stop the scheduler")
@click.option("--list", "list_jobs", is_flag=True, help="List scheduled jobs")
def scheduler_command(start, stop, list_jobs):
    """Manage the background reminder scheduler."""
    from wimlds.agents.event_ops.reminders_agent import RemindersAgent
    agent = RemindersAgent()
    if start:
        click.echo("Starting scheduler...")
        agent.start_scheduler()
        click.secho("Scheduler running", fg="green")
    elif stop:
        agent.stop_scheduler()
        click.secho("Scheduler stopped", fg="yellow")
    elif list_jobs:
        jobs = agent.list_jobs()
        if not jobs:
            click.echo("No scheduled jobs.")
        for job in jobs:
            click.echo(f"  {job['id']:<30} next: {job['next_run']}")


@cli.command("provision")
@click.option("--event-id", required=True)
def provision_command(event_id):
    """Provision Google Drive folder structure for an event."""
    from wimlds.scripts.provision_drive import provision_event_folders
    url = provision_event_folders(event_id)
    click.secho(f"Drive folder created: {url}", fg="green")


@cli.command("social")
@click.option("--event-id", required=True, help="Master Sheet row number (e.g. 4)")
@click.option("--stage", required=True, type=click.Choice(VALID_SOCIAL_STAGES), help="Which message stage to send")
@click.option("--channel", default="all", type=click.Choice(VALID_SOCIAL_CHANNELS), help="Which platform to send to")
@click.option("--dry-run", is_flag=True, default=False, help="Preview only - no real API calls")
@click.option("--preview", is_flag=True, default=False, help="Print the message text without sending")
@click.option("--wa-mode", default="auto", type=click.Choice(["auto", "twilio", "web"]), help="WhatsApp mode")
def social_command(event_id, stage, channel, dry_run, preview, wa_mode):
    """Run social and WhatsApp posting for an event."""
    if dry_run:
        click.secho("DRY-RUN MODE - no real posts will be made", fg="yellow", bold=True)
    event_data = _sheets_client().get_event(int(event_id))
    if preview:
        _preview_social_message(event_data, stage)
        return
    if channel != "all":
        _force_single_channel(event_data, channel)
    if channel == "whatsapp" or (channel == "all" and event_data.get("promote_whatsapp", "Y").upper() == "Y"):
        _run_whatsapp(event_data, stage, dry_run, wa_mode)
    if channel != "whatsapp":
        _run_social(event_data, stage, dry_run)
    click.secho(f"\nDone - {stage} posted", fg="green", bold=True)


@cli.command("langgraph")
@click.option("--event-id", required=True, help="Master Sheet row number, e.g. 3")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate - no writes, no emails, no real API calls")
@click.option("--resume", is_flag=True, default=False, help="Resume a halted or crashed pipeline")
@click.option("--from-stage", default=None, type=click.Choice(VALID_LG_STAGES, case_sensitive=False), help="Skip all stages before this one")
@click.option("--agent", default=None, type=click.Choice(VALID_LG_STAGES, case_sensitive=False), help="Run a single agent node only")
@click.option("--show-log", is_flag=True, default=False, help="Print the full audit log after completion")
def langgraph_command(event_id, dry_run, resume, from_stage, agent, show_log):
    """Run the LangGraph multi-agent orchestrator."""
    _, run_full_pipeline, run_single_agent = _langgraph_api()
    if agent:
        result = run_single_agent(event_id=event_id, agent_name=agent, dry_run=dry_run)
        if show_log:
            _print_audit_log(result.get("audit_log", []))
        if result.get("success"):
            click.secho("Completed successfully", fg="green")
            return
        click.secho(f"Agent failed: {result.get('error')}", fg="red")
        sys.exit(1)
    final = run_full_pipeline(event_id=event_id, dry_run=dry_run, resume=resume, from_stage=from_stage)
    if show_log:
        _print_audit_log(final.get("audit_log", []))
    if final.get("error"):
        click.secho(f"Pipeline failed: {final.get('error')}", fg="red")
        sys.exit(1)
    click.secho("Pipeline complete", fg="green")


@cli.command("analytics")
@click.option("--event-id", default=None, help="Master Sheet row number (e.g. 3)")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate - no writes, no emails, no real API calls")
@click.option("--backfill", is_flag=True, default=False, help="Re-run analytics for an already-completed event")
@click.option("--growth-only", is_flag=True, default=False, help="Print the 10k-member goal tracker only")
@click.option("--no-email", is_flag=True, default=False, help="Skip the completion email even on a real run")
def analytics_command(event_id, dry_run, backfill, growth_only, no_email):
    """Run the analytics workflow or growth report."""
    from wimlds.agents.post_event.analytics_agent import AnalyticsAgent
    agent = AnalyticsAgent(dry_run=dry_run)
    if growth_only:
        growth = agent.growth_report_only()
        click.echo(json.dumps(growth, indent=2))
        return
    if not event_id:
        click.secho("--event-id is required unless --growth-only is set.", fg="red")
        sys.exit(1)
    event_data = _sheets_client().get_event(int(event_id))
    if no_email:
        agent._send_completion_email = lambda *args, **kwargs: logger.info("Email skipped (--no-email)")
    result = agent.run_standalone(event_data, int(event_id)) if backfill else agent.run(event_data, int(event_id))
    if result.success:
        click.secho("Analytics complete", fg="green")
        return
    click.secho(f"Analytics failed: {result.error}", fg="red")
    sys.exit(1)


@cli.command("post-event-agent")
@click.option("--event-id", required=True, type=int, help="Master Sheet row number (e.g. 3)")
@click.option("--meeting-id", default=None, help="Zoom meeting ID")
@click.option("--platform", default="zoom", type=click.Choice(["zoom", "gmeet", "teams"]), show_default=True, help="Conferencing platform used")
@click.option("--transcript", default=None, metavar="PATH", help="Local transcript file path")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate all steps without making real API calls")
@click.option("--show-blog", is_flag=True, default=False, help="Print the generated blog post")
@click.option("--show-summary", is_flag=True, default=False, help="Print the structured LLM summary")
def post_event_agent_command(event_id, meeting_id, platform, transcript, dry_run, show_blog, show_summary):
    """Run the standalone post-event agent workflow."""
    from wimlds.agents.post_event.post_event_agent import PostEventAgent
    event_data = _load_post_event_event(event_id)
    result = PostEventAgent(dry_run=dry_run).run(event_data=event_data, meeting_id=meeting_id, platform=platform, transcript_path=transcript)
    if show_summary and result.summary:
        click.echo(json.dumps(result.summary, indent=2))
    if show_blog and result.blog_markdown:
        click.echo(result.blog_markdown)
    if result.errors:
        for err in result.errors:
            click.echo(f"- {err}")
        sys.exit(1)
    click.secho("Post-event agent complete", fg="green")


def _preview_social_message(event_data: dict, stage: str):
    from wimlds.config.message_templates import render_announcement, render_spotlight, render_logistics, render_final_bump
    from wimlds.agents.publishing.social_agent import _event_to_context
    ctx = _event_to_context(event_data)
    fn = {"announcement": render_announcement, "spotlight": render_spotlight, "logistics": render_logistics, "final_bump": render_final_bump}[stage]
    click.echo(fn(ctx))


def _force_single_channel(event_data: dict, channel: str):
    for ch in ["linkedin", "facebook", "x", "instagram", "meetup", "whatsapp"]:
        event_data[f"promote_{ch}"] = "Y" if ch == channel else "N"


def _run_social(event_data: dict, stage: str, dry_run: bool):
    from wimlds.agents.publishing.social_agent import SocialAgent
    agent = SocialAgent(dry_run=dry_run)
    fn = {"announcement": agent.post_announcement, "spotlight": agent.post_spotlight, "logistics": agent.post_logistics, "final_bump": agent.post_final_bump}[stage]
    result = fn(event_data)
    click.echo(result.data if result.success else result.error)


def _run_whatsapp(event_data: dict, stage: str, dry_run: bool, wa_mode: str):
    from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
    agent = WhatsAppAgent(dry_run=dry_run, mode=wa_mode)
    fn = {"announcement": agent.send_announcement, "spotlight": agent.send_spotlight, "logistics": agent.send_logistics, "final_bump": agent.send_final_bump}[stage]
    result = fn(event_data)
    agent.close()
    click.echo(result.data if result.success else result.error)


def _print_audit_log(audit_log: list):
    for entry in audit_log:
        detail = f" [{entry.get('detail', '')}]" if entry.get("detail") else ""
        click.echo(f"{entry.get('ts', '')[:19]} {entry.get('stage', '?'):<22} {entry.get('status', '?')}{detail}")


def _load_post_event_event(event_id: int) -> dict:
    from wimlds.core.sheets_client import sheets_client, _StubSheetsClient
    if not isinstance(sheets_client, _StubSheetsClient):
        try:
            return sheets_client.get_event(event_id)
        except Exception as exc:
            logger.warning(f"Could not load row {event_id}: {exc}")
    fixture_path = Path(__file__).parent / "tests" / "fixtures" / "sample_event.json"
    if fixture_path.exists():
        data = json.loads(fixture_path.read_text())
        data["_row_number"] = event_id
        return data
    return {"_row_number": event_id, "event_title": "Demo Event", "date": "15 Nov 2025"}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        sys.argv.insert(1, "event")
    cli()

