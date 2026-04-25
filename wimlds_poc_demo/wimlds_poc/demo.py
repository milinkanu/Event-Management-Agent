#!/usr/bin/env python3
"""
WiMLDS Pune — Zero-Credential POC Demo
=======================================
Runs the full 12-stage automation pipeline against local JSON data.
No API keys, no Google account, no Redis required.

Usage:
  python demo.py                          # full pipeline, event-id 3
  python demo.py --event-id 3            # explicit row
  python demo.py --agent poster          # single agent only
  python demo.py --agent social --stage t2d
  python demo.py --remind t2d            # simulate reminder firing
  python demo.py --post-event            # run post-event pipeline
  python demo.py --reset                 # clear all write-backs and start fresh
  python demo.py --show-output           # print everything written to sheet
"""

import sys, argparse, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.logger    import *
from core.data_store import load_event, get_written_back, reset_event
from agents.mock_agents import (
    run_validator, run_meetup_agent, run_qr_agent, run_poster_agent,
    run_social_agent, run_whatsapp_agent, run_partner_agent,
    run_conferencing_agent, run_reminders_agent, run_event_exec_agent,
    run_post_event_agent, run_analytics_agent,
)

STAGES = [
    ("validate",      "Validator"),
    ("meetup",        "Meetup Event Agent"),
    ("qr",            "QR Code Agent"),
    ("poster",        "Poster Agent"),
    ("social",        "Social Syndication"),
    ("whatsapp",      "WhatsApp Helper"),
    ("partner",       "Partner & Media"),
    ("conferencing",  "Conferencing Agent"),
    ("reminders",     "Reminders Agent"),
    ("event_exec",    "Event Execution"),
    ("post_event",    "Post-Event Agent"),
    ("analytics",     "Analytics Agent"),
]


def print_summary(row: int):
    wb = get_written_back(row)
    if not wb:
        info("No write-backs yet."); return
    banner("Sheet Write-Back Summary  (what would be written to Google Sheets)")
    skip = {"_last_updated"}
    for k, v in wb.items():
        if k in skip: continue
        short = str(v)[:80] + "…" if len(str(v)) > 80 else str(v)
        print(f"  {PRP}{BLD}{k:<35}{RST} {GRN}{short}{RST}")


def run_full_pipeline(event: dict, row: int):
    banner("WiMLDS Pune  —  Meetup Automation  POC Demo  —  Blueprint v9.0")
    print(f"\n  {BLU}Event    : {BLD}{event['event_title']}{RST}")
    print(f"  {BLU}Date     : {event['date']} ({event['day']}) {event['start_time_ist']}–{event['end_time_ist']} IST{RST}")
    print(f"  {BLU}Mode     : {event['mode']}  |  Venue: {event['venue_name']}{RST}")
    print(f"  {BLU}Speaker  : {event['speaker_name']} — {event.get('speaker_title','')} @ {event.get('speaker_org','')}{RST}")
    print(f"  {YLW}All external calls are MOCKED — no API keys needed{RST}\n")
    time.sleep(0.5)

    # Stage 0 — Validate
    if not run_validator(event): sys.exit(1)
    event = load_event(row)  # reload after each write-back

    # Stage 1 — Meetup
    run_meetup_agent(event, row); event = load_event(row)

    # Stage 2 — QR
    run_qr_agent(event, row); event = load_event(row)

    # Stage 3 — Poster
    run_poster_agent(event, row); event = load_event(row)

    # Stage 4 — Social announcement
    run_social_agent(event, row, "announcement"); event = load_event(row)

    # Stage 5 — WhatsApp
    run_whatsapp_agent(event, row, "announcement"); event = load_event(row)

    # Stage 6 — Partners
    run_partner_agent(event, row); event = load_event(row)

    # Stage 7 — Conferencing
    run_conferencing_agent(event, row); event = load_event(row)

    # Stage 8 — Reminders scheduler
    run_reminders_agent(event, row); event = load_event(row)

    # Stage 9 — Event Execution (simulated day-of)
    run_event_exec_agent(event, row); event = load_event(row)

    # Stage 10 — Post-Event
    run_post_event_agent(event, row); event = load_event(row)

    # Stage 11 — Analytics
    run_analytics_agent(event, row)

    # Final summary
    banner("✅  Pipeline Complete  —  All 12 Stages Passed")
    print(f"\n  {GRN}Output files written to:{RST} {Path(__file__).parent / 'output'}")
    output_dir = Path(__file__).parent / "output"
    for f in sorted(output_dir.iterdir()):
        print(f"  {GRY}  {f.name}{RST}")
    print()
    print_summary(row)
    print(f"\n  {YLW}Tip: run   python demo.py --show-output   to see this summary anytime{RST}")
    print(f"  {YLW}     run   python demo.py --reset         to run the demo again from scratch{RST}\n")


def main():
    ap = argparse.ArgumentParser(
        description="WiMLDS Pune — Zero-Credential POC Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo.py                          full pipeline
  python demo.py --agent poster           poster agent only
  python demo.py --agent social --stage t2d   T-2d spotlight blast
  python demo.py --remind t2d             simulate reminder firing
  python demo.py --post-event             post-event pipeline
  python demo.py --reset && python demo.py    fresh full run
  python demo.py --show-output            print sheet write-back summary
""")
    ap.add_argument("--event-id",    type=int, default=3, metavar="N",
                    help="Row number in event_data.json  (default: 3)")
    ap.add_argument("--agent",       metavar="NAME",
                    choices=["validate","meetup","qr","poster","social","whatsapp",
                             "partner","conferencing","reminders","event-exec",
                             "post-event","analytics"],
                    help="Run a single agent instead of the full pipeline")
    ap.add_argument("--stage",       default="announcement",
                    choices=["announcement","t2d","t1d","t2h"],
                    help="Social/WA stage (default: announcement)")
    ap.add_argument("--remind",      metavar="STAGE",
                    choices=["t2d","t1d","t2h"],
                    help="Simulate a reminder firing")
    ap.add_argument("--post-event",  action="store_true",
                    help="Run only the post-event pipeline")
    ap.add_argument("--reset",       action="store_true",
                    help="Clear all write-backs so you can run the demo from scratch")
    ap.add_argument("--show-output", action="store_true",
                    help="Print sheet write-back summary and exit")
    args = ap.parse_args()

    row = args.event_id

    if args.reset:
        reset_event(row)
        ok(f"Write-backs cleared for event-id {row}. Run demo.py again for a fresh run.")
        return

    if args.show_output:
        print_summary(row); return

    event = load_event(row)

    if args.remind:
        stage_map = {"t2d": "t2d", "t1d": "t1d", "t2h": "t2h"}
        s = stage_map[args.remind]
        banner(f"Simulating reminder: {s.upper()}")
        run_social_agent(event, row, s)
        run_whatsapp_agent(event, row, s)
        return

    if args.post_event:
        banner("Post-Event Pipeline")
        run_post_event_agent(event, row)
        run_analytics_agent(load_event(row), row)
        print_summary(row); return

    if args.agent:
        banner(f"Single Agent: {args.agent}")
        dispatch = {
            "validate":     lambda: run_validator(event),
            "meetup":       lambda: run_meetup_agent(event, row),
            "qr":           lambda: run_qr_agent(event, row),
            "poster":       lambda: run_poster_agent(event, row),
            "social":       lambda: run_social_agent(event, row, args.stage),
            "whatsapp":     lambda: run_whatsapp_agent(event, row, args.stage),
            "partner":      lambda: run_partner_agent(event, row),
            "conferencing": lambda: run_conferencing_agent(event, row),
            "reminders":    lambda: run_reminders_agent(event, row),
            "event-exec":   lambda: run_event_exec_agent(event, row),
            "post-event":   lambda: run_post_event_agent(event, row),
            "analytics":    lambda: run_analytics_agent(event, row),
        }
        dispatch[args.agent]()
        print_summary(row); return

    run_full_pipeline(event, row)


if __name__ == "__main__":
    main()
