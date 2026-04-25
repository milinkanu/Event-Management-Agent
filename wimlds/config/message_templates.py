"""
config/message_templates.py
============================
Message templates and render helpers for all announcement stages.
Used by SocialAgent, WhatsAppAgent, PostEventAgent, and Notifier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ─────────────────────────────────────────────────────────────────────────────
# EventContext dataclass — passed to all render_* functions
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EventContext:
    event_title:         str = ""
    subtitle:            str = ""
    day:                 str = ""
    date:                str = ""
    start_time:          str = ""
    end_time:            str = ""
    venue_name:          str = ""
    venue_address:       str = ""
    entrance_note:       str = ""
    parking_info:        str = ""
    laptop_required:     str = "No"
    wifi_note:           str = ""
    host_name:           str = ""
    host_phone:          str = ""
    speaker_name:        str = ""
    speaker_title:       str = ""
    speaker_org:         str = ""
    speaker_achievements: List[str] = field(default_factory=list)
    learn_bullets:       List[str] = field(default_factory=list)
    scope_one_liner:     str = ""
    meetup_url:          str = ""
    conference_link:     str = ""
    mode:                str = "In-Person"
    series:              str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Announcement (Stage 1 — event published)
# ─────────────────────────────────────────────────────────────────────────────

def render_announcement(ctx: EventContext) -> str:
    lines = [
        f"📢 We're thrilled to announce our next WiMLDS Pune event!",
        "",
        f"🎯 *{ctx.event_title}*",
    ]
    if ctx.subtitle:
        lines.append(f"   {ctx.subtitle}")
    lines += [""]

    if ctx.speaker_name:
        lines.append(f"🎙️ Speaker: {ctx.speaker_name}")
        if ctx.speaker_title and ctx.speaker_org:
            lines.append(f"   {ctx.speaker_title} @ {ctx.speaker_org}")
        if ctx.speaker_achievements:
            lines.append(f"   ✨ {'; '.join(ctx.speaker_achievements[:2])}")
        lines.append("")

    if ctx.learn_bullets:
        lines.append("📚 What you'll learn:")
        for b in ctx.learn_bullets[:4]:
            lines.append(f"   ✅ {b}")
        lines.append("")

    lines += [
        f"📅 {ctx.day}, {ctx.date}  |  {ctx.start_time}–{ctx.end_time} IST",
    ]

    if ctx.mode in ("In-Person", "Hybrid"):
        lines.append(f"📍 {ctx.venue_name}")
    if ctx.mode in ("Online", "Hybrid") and ctx.conference_link:
        lines.append(f"💻 Join: {ctx.conference_link}")

    lines += [""]

    if ctx.meetup_url:
        lines.append(f"👉 RSVP (free): {ctx.meetup_url}")

    lines += [
        "",
        "#WiMLDS #WiMLDSPune #MachineLearning #DataScience #WomenInTech #Pune",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# T-2 Days — Speaker Spotlight
# ─────────────────────────────────────────────────────────────────────────────

def render_spotlight(ctx: EventContext) -> str:
    lines = [
        f"🌟 Speaker Spotlight — {ctx.event_title}",
        "",
    ]
    if ctx.speaker_name:
        lines.append(f"Meet our speaker: *{ctx.speaker_name}*")
        if ctx.speaker_title and ctx.speaker_org:
            lines.append(f"{ctx.speaker_title} @ {ctx.speaker_org}")
        if ctx.speaker_achievements:
            for a in ctx.speaker_achievements[:3]:
                lines.append(f"• {a}")
        lines.append("")

    if ctx.scope_one_liner:
        lines += [f"💡 {ctx.scope_one_liner}", ""]

    lines += [
        f"⏰ In just 2 days! {ctx.day}, {ctx.date}  |  {ctx.start_time} IST",
    ]
    if ctx.meetup_url:
        lines.append(f"🔗 RSVP: {ctx.meetup_url}")

    lines += ["", "#WiMLDS #WiMLDSPune #AI #ML #WomenInTech"]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# T-1 Day — Logistics
# ─────────────────────────────────────────────────────────────────────────────

def render_logistics(ctx: EventContext) -> str:
    lines = [
        f"📋 Event Tomorrow! — {ctx.event_title}",
        "",
        f"📅 {ctx.day}, {ctx.date}  |  {ctx.start_time}–{ctx.end_time} IST",
        "",
    ]

    if ctx.mode in ("In-Person", "Hybrid"):
        lines.append(f"📍 Venue: {ctx.venue_name}")
        if ctx.venue_address:
            lines.append(f"   {ctx.venue_address}")
        if ctx.entrance_note:
            lines.append(f"🚪 Entry: {ctx.entrance_note}")
        if ctx.parking_info:
            lines.append(f"🅿️  Parking: {ctx.parking_info}")
        lines.append("")

    if ctx.mode in ("Online", "Hybrid"):
        link = ctx.conference_link or "Will be shared in the Meetup event page"
        lines += [f"💻 Join link: {link}", ""]

    if ctx.laptop_required and ctx.laptop_required.lower() not in ("no", "n", ""):
        lines.append(f"💻 Bring your laptop: {ctx.laptop_required}")
    if ctx.wifi_note:
        lines.append(f"📶 Wi-Fi: {ctx.wifi_note}")

    if ctx.host_name:
        lines.append(f"👤 Contact on-site: {ctx.host_name} ({ctx.host_phone})")

    lines += [
        "",
        "See you there! 🚀",
        "",
        "#WiMLDS #WiMLDSPune",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# T-2 Hours — Final Bump
# ─────────────────────────────────────────────────────────────────────────────

def render_final_bump(ctx: EventContext) -> str:
    lines = [
        f"⏰ Starting in 2 hours! — {ctx.event_title}",
        "",
        f"📅 Today, {ctx.date}  |  {ctx.start_time} IST",
    ]
    if ctx.mode in ("In-Person", "Hybrid"):
        lines.append(f"📍 {ctx.venue_name}")
    if ctx.mode in ("Online", "Hybrid"):
        link = ctx.conference_link or "Check the Meetup event page"
        lines.append(f"💻 {link}")
    lines += [
        "",
        "Don't forget to RSVP if you haven't — see you soon! 🎉",
        "",
        "#WiMLDS #WiMLDSPune",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Missing-fields alert email
# ─────────────────────────────────────────────────────────────────────────────

def render_missing_info_email(
    owner_name: str,
    event_title: str,
    missing_fields: list,
) -> tuple[str, str]:
    subject = f"[WiMLDS Action Required] Missing info — {event_title}"
    body = f"""Hi {owner_name or 'Organiser'},

The WiMLDS automation pipeline has paused for the following event because some required fields are missing:

  Event: {event_title}

Missing fields:
{chr(10).join(f'  • {f}' for f in missing_fields)}

Please fill in these fields in the Master Sheet and then re-run the pipeline with:
  python run.py langgraph --event-id <row> --resume

Thank you!
WiMLDS Automation Orchestrator
"""
    return subject, body


# ─────────────────────────────────────────────────────────────────────────────
# Post-event LinkedIn template
# ─────────────────────────────────────────────────────────────────────────────

POST_EVENT_LINKEDIN_TEMPLATE = """🙏 Thank you for joining us at {event_title}!

It was an incredible session — {venue_name} was buzzing with energy as {speaker_name} ({speaker_title}, {speaker_org}) walked us through the topic.

{highlights_block}

📝 Read the full blog recap: {blog_link}

A big thank you to {venue_sponsor} for hosting us{gift_sponsor_line} and to everyone who showed up, asked great questions, and made it memorable.

{c_level_tags}

👉 Stay connected: {meetup_url}

#WiMLDS #WiMLDSPune #MachineLearning #WomenInTech #Pune #CommunityEvent
"""



