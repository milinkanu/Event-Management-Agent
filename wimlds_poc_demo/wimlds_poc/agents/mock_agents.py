"""
All 11 mock agents — every external API call is simulated with realistic
output. Zero credentials required.
"""
import time, random, json
from pathlib import Path
from datetime import datetime, timedelta

_ROOT      = Path(__file__).parent.parent
OUTPUT_DIR = _ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

import sys
sys.path.insert(0, str(_ROOT))
from core.logger import *
from core.data_store import write_field, write_fields, set_flag

def _pause(lo=0.2, hi=0.5): time.sleep(random.uniform(lo, hi))
def _fid():  return ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=18))
def _drive(name): return f"https://drive.google.com/file/d/{_fid()}/view  [MOCK:{name}]"
def _meetup_id(): return str(random.randint(300_000_000, 399_999_999))
def _save(name, text):
    p = OUTPUT_DIR / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ── STAGE 0 — Validator ───────────────────────────────────────────────────────
REQUIRED = ["series","event_title","date","day","start_time_ist","end_time_ist",
            "mode","venue_name","venue_address","speaker_name",
            "speaker_highest_qualification","speaker_tier1_institution",
            "speaker_special_achievements","c_level_linkedin_handles"]

def run_validator(event: dict) -> bool:
    section("STAGE 0 — Validator", CYN)
    step("Validator", "Checking all required fields …")
    _pause()
    missing = [f for f in REQUIRED if not str(event.get(f,"")).strip()]
    if missing:
        fail(f"HALTED — missing: {missing}")
        end_section(RED); return False
    ok(f"All {len(REQUIRED)} required fields present")
    ok(f"Title : {event['event_title']}")
    ok(f"Date  : {event['date']} ({event['day']}) {event['start_time_ist']}–{event['end_time_ist']} IST")
    ok(f"Mode  : {event['mode']}  |  Venue: {event['venue_name']}")
    ok(f"Speaker: {event['speaker_name']} — {event.get('speaker_title','')}, {event.get('speaker_org','')}")
    end_section(); return True


# ── STAGE 1 — Meetup Event Agent ─────────────────────────────────────────────
def run_meetup_agent(event: dict, row: int) -> dict:
    section("STAGE 1 — Meetup Event Agent", BLU)
    step("MeetupAgent", "OAuth 2.0 handshake …")
    _pause(); mock_call("Meetup OAuth","POST /oauth2/access","token=***mock***")
    step("MeetupAgent", f"Creating event …")
    _pause(0.4, 0.9)
    eid  = _meetup_id()
    eurl = f"https://meetup.com/WiMLDS-Pune/events/{eid}  [MOCK]"
    mock_call("Meetup API", f"POST /WiMLDS-Pune/events", f"id={eid}")
    ok(f"Event live → ID {eid}")
    write_back("meetup_event_url", eurl)
    write_back("meetup_event_id",  eid)
    write_fields(row, {"meetup_event_url": eurl, "meetup_event_id": eid})
    end_section(BLU)
    return {"meetup_event_url": eurl, "meetup_event_id": eid}


# ── STAGE 2 — QR Agent ────────────────────────────────────────────────────────
def run_qr_agent(event: dict, row: int) -> dict:
    section("STAGE 2 — QR Code Agent", CYN)
    url = event.get("meetup_event_url","https://meetup.com/WiMLDS-Pune").split("  [")[0]
    step("QRAgent", f"Generating QR for: {url[:55]} …")
    _pause()
    qr_url = _drive("QR_demo.png")
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=3,
                           error_correction=qrcode.constants.ERROR_CORRECT_H)
        qr.add_data(url); qr.make(fit=True)
        img = qr.make_image(fill_color="#4C1D95", back_color="white")
        qr_path = OUTPUT_DIR / "QR_demo.png"
        img.save(str(qr_path))
        ok(f"QR PNG generated → {qr_path}")
        qr_url = f"file://{qr_path}  [LOCAL — would upload to Drive]"
    except ImportError:
        warn("qrcode lib not installed → using mock URL")
    mock_call("Drive API","files.create QR_demo.png → /02_Output/02_QR/", qr_url[:55])
    write_back("qr_drive_url", qr_url)
    write_field(row, "qr_drive_url", qr_url)
    end_section(); return {"qr_drive_url": qr_url}


# ── STAGE 3 — Poster Agent ────────────────────────────────────────────────────
def run_poster_agent(event: dict, row: int) -> dict:
    section("STAGE 3 — Poster Agent", PRP)
    step("PosterAgent","Composing 1080×1350 brand-safe poster …")
    _pause(0.3, 0.7)

    poster_path = _make_poster(event)
    poster_url  = _drive("Poster_Final.png")
    mock_call("Drive API","files.create Poster_Final.png → /01_Poster_Final/", poster_url[:55])
    ok(f"Poster rendered → {poster_path}")
    info("Zones: QR(top-left) | WiMLDS logo(top-right) | Title | Timing pill(pink)")
    info(f"       Speaker circle | Venue(no host/mode/series) | Partner logos(footer)")

    step("PosterAgent","Sending approval email to speaker + venue sponsor …")
    _pause(0.2)
    mock_call("SendGrid","POST /mail/send → speaker + sponsor + organiser","202 Accepted")
    ok("Approval email sent")
    warn("DEMO: auto-approving (real run waits for email reply)")
    _pause(0.3); ok("Poster APPROVED ✓")

    step("PosterAgent","Uploading poster to Meetup event image …")
    _pause(0.2)
    mock_call("Meetup API",f"POST /events/{event.get('meetup_event_id','xxx')}/photos","uploaded")
    write_fields(row, {"poster_drive_url": poster_url, "poster_status":"Uploaded",
                       "poster_meetup_url":"https://meetup.com/photo/poster_mock [MOCK]"})
    write_back("poster_drive_url", poster_url)
    write_back("poster_status",    "Uploaded")
    end_section(PRP)
    return {"poster_drive_url": poster_url}


def _make_poster(event: dict) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 1080, 1350
        img  = Image.new("RGB",(W,H),(255,255,255))
        draw = ImageDraw.Draw(img)
        for y in range(H):  # purple→white gradient
            t  = y/H
            rv = int(76 + (255-76)*t); gv = int(29+(255-29)*t); bv = int(149+(255-149)*t)
            draw.line([(0,y),(W,y)], fill=(rv,gv,bv))
        draw.rectangle([(0,0),(W,140)], fill=(76,29,149))          # top bar
        draw.rectangle([(15,12),(125,128)], outline=(255,255,255), width=2)  # QR box
        draw.text((35,58), "QR", fill=(255,255,255))
        draw.text((W-195,48), "WiMLDS PUNE", fill=(255,255,255))

        def ct(text, y, sz=32, col=(76,29,149), bold=False):
            fn = "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf".format("-Bold" if bold else "")
            try: f = ImageFont.truetype(fn, sz)
            except Exception: f = ImageFont.load_default()
            bb = draw.textbbox((0,0), text, font=f)
            draw.text(((W-(bb[2]-bb[0]))//2, y), text, fill=col, font=f)

        ct(event["event_title"][:46], 158, 36, (76,29,149), bold=True)
        ct(event.get("subtitle","")[:58], 210, 21, (55,65,81))
        timing = f"{event['day']}  ·  {event['date']}  ·  {event['start_time_ist']}–{event['end_time_ist']} IST"
        draw.rounded_rectangle([(70,272),(W-70,332)], radius=28, fill=(236,72,153))
        ct(timing, 282, 22, (255,255,255))
        cx = W//2 - 70
        draw.ellipse([(cx,365),(cx+140,505)], fill=(76,29,149))
        ct(event["speaker_name"], 526, 30, (31,41,55), bold=True)
        ct(event.get("speaker_title",""), 572, 20, (107,114,128))
        ct(event.get("speaker_org",""),   600, 20, (76,29,149))
        draw.text((40,840), f"📍 {event['venue_name']}", fill=(31,41,55))
        draw.text((40,876), event["venue_address"][:55], fill=(107,114,128))
        ct("ABI Group  |  PKC  |  GPU Community  |  Startup Prime", 1120, 18, (107,114,128))
        draw.rectangle([(0,H-12),(W,H)], fill=(236,72,153))
        path = str(OUTPUT_DIR / "Poster_Final_demo.png")
        img.save(path); return path
    except Exception:
        path = str(OUTPUT_DIR / "Poster_demo.txt")
        Path(path).write_text(
            f"POSTER PREVIEW\n{'='*40}\n"
            f"Title:   {event['event_title']}\n"
            f"Timing:  {event['day']} {event['date']} {event['start_time_ist']} IST\n"
            f"Speaker: {event['speaker_name']}\n"
            f"Venue:   {event['venue_name']}\n"
        )
        return path


# ── STAGE 4 — Social Syndication Agent ───────────────────────────────────────
def run_social_agent(event: dict, row: int, stage: str = "announcement") -> dict:
    labels = {"announcement":"Announcement","t2d":"T-2d Speaker Spotlight",
              "t1d":"T-1d Logistics","t2h":"T-2h Final Bump"}
    section(f"STAGE 4 — Social Agent  [{labels.get(stage,stage)}]", GRN)
    text = _social_text(event, stage)
    _save(f"social_{stage}.txt", text)
    ok(f"Copy saved → output/social_{stage}.txt")
    info("Preview: " + text.splitlines()[0][:80])
    divider()

    channels = []
    if event.get("promote_linkedin","Y")=="Y": channels.append("LinkedIn")
    if event.get("promote_facebook","Y")=="Y": channels.append("Facebook")
    if event.get("promote_x","Y")=="Y":        channels.append("X/Twitter")
    if event.get("promote_instagram","Y")=="Y":channels.append("Instagram")
    for ch in channels:
        _pause(0.15,0.35)
        mock_call(f"{ch} API","create post", f"post_id=mock_{random.randint(10000,99999)}")
    mock_call("Meetup API","Contact Attendees message","delivered")

    flags = {"announcement":"announce_sent","t2d":"tminus2_sent",
             "t1d":"tminus1_sent","t2h":"tminus2h_sent"}
    if stage in flags:
        set_flag(row, flags[stage]); write_back(flags[stage], "Y")
    ok(f"Posted to {len(channels)} channels + Meetup attendees")
    end_section(GRN)
    return {"channels": channels}


def _social_text(e: dict, stage: str) -> str:
    url = e.get("meetup_event_url","https://meetup.com/WiMLDS-Pune")
    if stage == "announcement":
        return (f"🚀 Next WiMLDS Pune: {e['event_title']}\n\n"
                f"📅 {e['day']} · {e['date']} · {e['start_time_ist']}–{e['end_time_ist']} IST\n"
                f"📍 {e['venue_name']}, {e['venue_address']}\n\n"
                f"🎙️ Speaker: {e['speaker_name']}, {e.get('speaker_title','')} @ {e.get('speaker_org','')}\n\n"
                f"💡 {e.get('subtitle','')}\n\n🔗 RSVP (free): {url}\n\n"
                f"#WiMLDS #Pune #AI #MachineLearning #WomenInTech")
    if stage == "t2d":
        bullets = "\n".join(f"✅ {b}" for b in e.get("_learn_bullets",[]))
        ach = e.get("speaker_special_achievements","").replace(";","\n•")
        return (f"🎙️ Speaker Spotlight: {e['speaker_name']}\n"
                f"{e.get('speaker_title','')} @ {e.get('speaker_org','')}\n\n"
                f"• {ach}\n\nWhat you'll learn:\n{bullets}\n\n"
                f"📅 {e['day']} · {e['date']} · {e['start_time_ist']} IST\n📍 {e['venue_name']}\n"
                f"🔗 {url}\n#WiMLDS #Pune #AI")
    if stage == "t1d":
        return (f"⏰ Tomorrow — {e['event_title']}\n\n"
                f"📋 Logistics:\n🔐 {e.get('entrance_note','Standard entry')}\n"
                f"🅿️ {e.get('parking_info','')}\n💻 Laptop: {e.get('laptop_required','No')}\n"
                f"👤 Host: {e.get('host_name','')} ({e.get('host_phone','')})\n\n"
                f"📅 {e['date']} · {e['start_time_ist']}–{e['end_time_ist']} IST\n"
                f"📍 {e['venue_name']}\n#WiMLDS #Pune")
    if stage == "t2h":
        conf = e.get("conference_link","")
        cl   = f"\n💻 Join online: {conf}\n" if e.get("mode") in ("Online","Hybrid") and conf else ""
        return (f"🚪 See you in 2 hours! — {e['event_title']}\n"
                f"📅 Today · {e['start_time_ist']}–{e['end_time_ist']} IST\n"
                f"📍 {e['venue_name']}{cl}\n"
                f"🔐 {e.get('entrance_note','')}\n👤 {e.get('host_name','')} {e.get('host_phone','')}\n"
                f"#WiMLDS #Pune")
    return f"WiMLDS Pune — {e['event_title']}"


# ── STAGE 5 — WhatsApp Helper ─────────────────────────────────────────────────
def run_whatsapp_agent(event: dict, row: int, stage: str = "announcement") -> dict:
    section("STAGE 5 — WhatsApp Helper Agent", GRN)
    groups = [g.strip() for g in event.get("meetup_groups_list","").split(",") if g.strip()]
    step("WAHelper", f"Targeting {len(groups)} WA groups  [stage: {stage}]")
    info(f"Groups: {', '.join(groups)}")
    warn("DEMO: semi-manual confirm bypassed (real run opens WhatsApp Web per group)")
    for g in groups:
        _pause(0.1,0.25)
        mock_call("WhatsApp Web", f"Send → {g}", "✓ delivered [simulated]")
    set_flag(row, "whatsapp_groups_posted"); write_back("whatsapp_groups_posted","Y")
    ok(f"Messages delivered to {len(groups)} WA groups")
    end_section(GRN)
    return {"groups_sent": len(groups)}


# ── STAGE 6 — Partner Agent ───────────────────────────────────────────────────
DEMO_PARTNERS = [
    ("Ananya Mehta",  "ananya@aitechpune.in",  "AI Tech Pune"),
    ("Rohan Joshi",   "rohan@mlwomen.org",     "ML Women Network"),
    ("Kavita Singh",  "kavita@datastudio.co",  "Data Studio"),
    ("Arjun Patel",   "arjun@startupprime.in", "Startup Prime"),
]

def run_partner_agent(event: dict, row: int) -> dict:
    section("STAGE 6 — Partner & Media Agent", CYN)
    step("PartnerAgent", f"Sending personalised UTM-tracked emails to {len(DEMO_PARTNERS)} partners …")
    for name, email, org in DEMO_PARTNERS:
        _pause(0.15,0.35)
        utm = f"utm_source={org.lower().replace(' ','_')}&utm_medium=email&utm_campaign=partner"
        mock_call("SendGrid", f"→ {email}", f"subject: You're invited — {event['event_title'][:28]}…")
        info(f"  RSVP link: …?{utm[:60]}")
    set_flag(row, "partners_notified"); write_back("partners_notified","Y")
    ok(f"{len(DEMO_PARTNERS)} partner emails sent with UTM tracking")
    end_section(); return {"partners": len(DEMO_PARTNERS)}


# ── STAGE 7 — Conferencing Agent ─────────────────────────────────────────────
def run_conferencing_agent(event: dict, row: int) -> dict:
    section("STAGE 7 — Conferencing Agent", YLW)
    mode = event.get("mode","In-Person")
    if mode == "In-Person":
        ok("In-Person event — no conferencing setup required")
        end_section(YLW); return {"conference_link": ""}
    step("ConfAgent", f"Creating Zoom meeting (mode={mode}) …")
    _pause(0.4,0.9)
    mid  = str(random.randint(8_000_000_000, 8_999_999_999))
    pwd  = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZabcdef23456789', k=8))
    link = f"https://zoom.us/j/{mid}?pwd={pwd}  [MOCK]"
    mock_call("Zoom API", "POST /users/me/meetings", f"id={mid}")
    ok(f"Meeting created: {mid}")
    divider()
    for item in ["Waiting room: ON","Passcode: ON","Cloud recording: ON (auto-start)",
                 "Live transcription: ON","Save chat: ON","Host + Co-host: assigned"]:
        ok(f"  Appendix C — {item}")
    if mode in ("Online","Hybrid"):
        _pause(0.2)
        mock_call("Meetup API", f"PATCH /events/{event.get('meetup_event_id','xxx')} → add conf link","updated")
        ok("Conference link injected into Meetup description")
    write_field(row, "conference_link", link); write_back("conference_link", link)
    end_section(YLW); return {"conference_link": link}


# ── STAGE 8 — Reminders Agent ─────────────────────────────────────────────────
def run_reminders_agent(event: dict, row: int) -> dict:
    section("STAGE 8 — Reminders Agent (APScheduler)", BLU)
    try:
        from dateutil import parser as dtp
        from datetime import timezone as _tz, timedelta as _td
        IST = _tz(_td(hours=5, minutes=30))
        dt  = dtp.parse(f"{event['date']} {event['start_time_ist']}").replace(tzinfo=IST)
    except Exception:
        dt = datetime.now()
    t2d = dt - timedelta(days=2)
    t1d = dt - timedelta(days=1)
    t2h = dt - timedelta(hours=2)
    step("Reminders", "Registering 3 scheduled jobs …")
    _pause(0.2)
    jobs = [
        (f"T-2d  →  {t2d.strftime('%d %b %Y %H:%M IST')}", "Speaker Spotlight → all channels"),
        (f"T-1d  →  {t1d.strftime('%d %b %Y %H:%M IST')}", "Logistics Reminder → all channels"),
        (f"T-2h  →  {t2h.strftime('%d %b %Y %H:%M IST')}", "Final Bump (+conf link) → all channels"),
    ]
    for when, what in jobs:
        mock_call("APScheduler", f"add_job  {when}", what)
    ok("3 jobs registered with IST timezone & idempotent flag guards")
    warn("DEMO: jobs registered but won't fire (event date is in the future)")
    info("Simulate firing:  python demo.py --event-id 3 --remind t2d")
    end_section(BLU); return {"jobs_scheduled": 3}


# ── STAGE 9 — Event Execution Agent ──────────────────────────────────────────
def run_event_exec_agent(event: dict, row: int) -> dict:
    section("STAGE 9 — Event Execution Agent", YLW)
    step("EventExec","Running day-of checklist …")
    _pause(0.2)
    checks = [
        ("Conf link present in sheet",     bool(event.get("conference_link"))),
        ("Recording ON verified",          True),
        ("Transcription / captions ON",    True),
        ("Chat saving ON",                 True),
        ("Host + Co-host assigned",        True),
        ("Speaker material form sent",     True),
    ]
    all_ok = True
    for chk, passed in checks:
        if passed: ok(f"  {chk}")
        else: warn(f"  {chk}  ← NOT VERIFIED"); all_ok = False
    step("EventExec","Archiving speaker PPT to Drive …")
    _pause(0.2)
    mock_call("Drive API","files.create SpeakerSlides.pdf → /04_Presentations/","uploaded")
    ok("Materials archived")
    end_section(YLW); return {"checklist_ok": all_ok}


# ── STAGE 10 — Post-Event Agent ───────────────────────────────────────────────
TRANSCRIPT = """
[00:00] Welcome to WiMLDS Pune — RAG Systems in Production with Aditya Kulkarni, Google DeepMind.
[02:10] Most RAG failures come from poor chunking. Fixed-size chunks ignore semantic boundaries —
        we'll cover semantic chunking that improves retrieval recall by 23%+.
[15:30] Vector DB trade-offs: Pinecone (managed scale), Chroma (local dev), FAISS (custom ANN).
[32:00] Evaluation: RAGAS metrics — faithfulness, answer relevancy, context precision.
[48:20] Q: Multi-hop reasoning? A: You need a re-ranking step + step-back prompting loop.
[58:00] Thank you all! Slides & recording shared in the Meetup community group.
"""

def run_post_event_agent(event: dict, row: int) -> dict:
    section("STAGE 10 — Post-Event Agent", PRP)

    # Transcript
    _save("transcript_demo.txt", TRANSCRIPT)
    step("PostEvent","Uploading transcript to Drive …"); _pause()
    t_url = _drive("transcript.txt")
    mock_call("Drive API","files.create transcript.txt → /04_Transcript/", t_url[:55])

    # LLM blog
    step("PostEvent","Calling LLM → transcript-to-blog pipeline …")
    _pause(0.7,1.4)
    blog  = _blog(event)
    _save("blog_draft.md", blog)
    b_url = _drive("blog_draft.md")
    mock_call("Claude API","POST /v1/messages  (transcript → blog)","~2 000 tokens")
    mock_call("Drive API","files.create blog_draft.md → /05_Blogs_Drafts/", b_url[:55])
    ok("Blog generated → output/blog_draft.md")
    info(f"Preview: {blog.splitlines()[0]}")

    # LinkedIn (NO closed links)
    step("PostEvent","Publishing LinkedIn gratitude post …"); _pause(0.3)
    li = _linkedin_post(event, b_url)
    _save("linkedin_post.txt", li)
    mock_call("LinkedIn API","POST /ugcPosts (4-5 photos + gratitude + C-level tags)",
              "urn:li:ugcPost:mock")
    ok("LinkedIn post published — recording/slides NOT included (closed-sharing rule)")

    # Meetup (attendees only — WITH resources)
    step("PostEvent","Posting resources to Meetup attendees only …"); _pause()
    mock_call("Meetup API","Contact Attendees → recording + transcript + slides","delivered")
    ok("Resources shared with Meetup RSVPs (closed to attendees only)")

    # WhatsApp (closed WA groups only)
    step("PostEvent","Sharing in CLOSED WA groups …"); _pause()
    groups = [g.strip() for g in event.get("meetup_groups_list","").split(",") if g.strip()]
    for g in groups:
        mock_call("WhatsApp Web", f"→ {g}  (recording+slides+transcript)", "✓ [simulated]")
    divider()
    ok("🔒 CLOSED SHARING enforced — links NOT on public social channels")

    write_fields(row, {"transcript_link": t_url, "blog_link": b_url,
                       "post_event_completed":"Y","post_event_update_sent":"Y"})
    write_back("transcript_link", t_url)
    write_back("blog_link",       b_url)
    write_back("post_event_completed","Y")
    end_section(PRP)
    return {"blog_link": b_url, "transcript_link": t_url}


def _blog(e: dict) -> str:
    return f"""# {e['event_title']}
*WiMLDS Pune | {e['series']} | {e['date']}*

---

## Summary

WiMLDS Pune hosted an outstanding session on RAG Systems in Production with
{e['speaker_name']}, {e.get('speaker_title','')} at {e.get('speaker_org','')}.
The session opened by addressing why most RAG implementations fail in production:
poor chunking, naive retrieval, and absent evaluation frameworks.

---

## Top 5 Takeaways

1. **Semantic chunking beats fixed-size** — improves retrieval recall by 23%+ on long documents.
2. **Choose your vector DB carefully** — Pinecone (managed), Chroma (local dev), FAISS (custom).
3. **Evaluate with RAGAS** — faithfulness, answer relevancy, context precision.
4. **Re-ranking reduces hallucinations** — cross-encoder re-ranker before the final LLM call.
5. **Multi-hop reasoning needs an agent loop** — step-back prompting + iterative retrieval.

---

## Key Insights

The session challenged the audience to treat RAG as an engineering problem first — latency
budgets, cost per query, and fallback strategies are first-class concerns, not afterthoughts.

---

## Thank You

Huge thanks to **{e['speaker_name']}** and to **{e.get('venue_sponsor_name','our venue')}**
for hosting us.

👉 [Join WiMLDS Pune]({e.get('meetup_event_url','https://meetup.com/WiMLDS-Pune').split('  [')[0]})

*Recording & slides available in the Meetup group and closed WA community.*

#WiMLDS #Pune #RAG #MachineLearning #WomenInTech
"""


def _linkedin_post(e: dict, blog_url: str) -> str:
    tags = " ".join(f"@{h.strip()}" for h in e.get("c_level_linkedin_handles","").split(",") if h.strip())
    return f"""✨ Thank you, {e['event_title']}!

What an incredible session at {e['venue_name']}!

🎙️ Huge thanks to {e['speaker_name']} ({e.get('speaker_title','')} @ {e.get('speaker_org','')})
   for the deep-dive into RAG Systems in Production.

🏢 Thank you {e.get('venue_sponsor_name','our venue')} for hosting.
🙏 Special thanks to security, housekeeping & IT staff!

📚 Blog recap: {blog_url.split('  [')[0]}
   [Recording & slides shared in the Meetup community group]

👉 Not yet a member? {e.get('meetup_event_url','https://meetup.com/WiMLDS-Pune').split('  [')[0]}

{tags}

#WiMLDS #Pune #AI #MachineLearning #WomenInTech #RAG #Community"""


# ── STAGE 11 — Analytics Agent ────────────────────────────────────────────────
def run_analytics_agent(event: dict, row: int) -> dict:
    section("STAGE 11 — Analytics Agent", RED)
    step("Analytics","Aggregating KPIs from all platform responses …")
    _pause(0.4,0.9)
    kpis = {
        "Event":                event["event_title"],
        "Date":                 event["date"],
        "Series":               event["series"],
        "Mode":                 event["mode"],
        "RSVPs (Meetup)":       str(random.randint(55, 80)),
        "Showups (actual)":     str(random.randint(40, 60)),
        "LinkedIn Reactions":   str(random.randint(90, 220)),
        "Facebook Reactions":   str(random.randint(30, 90)),
        "Twitter Impressions":  str(random.randint(500, 2000)),
        "Blog Views (7d)":      str(random.randint(100, 450)),
        "Announce on time":     "Y",
        "T-2d on time":         "Y",
        "T-1d on time":         "Y",
        "T-2h on time":         "Y",
        "Partners emailed":     str(len(DEMO_PARTNERS)),
        "WA Groups reached":    str(len([g for g in event.get("meetup_groups_list","").split(",") if g.strip()])),
    }
    _save("kpi_report.json", json.dumps(kpis, indent=2))
    info("KPI Report:")
    for k, v in kpis.items():
        info(f"  {k:<28} {GRN}{v}{RST}")
    divider()
    mock_call("Looker Studio","Data source refresh triggered","dashboard updated")
    mock_call("Metabase",     "Cache invalidated","200 OK")
    mock_call("SendGrid",     "Completion email → organiser","202 Accepted")
    write_field(row, "event_status","Completed"); write_back("event_status","Completed")
    ok("KPI report → output/kpi_report.json")
    ok("Dashboards refreshed. Completion email sent to organiser ✓")
    end_section(RED); return {"kpis": kpis}
