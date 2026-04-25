# 📖 WiMLDS Pune Automation System — User Guide

> **For organizers, team members, and technical contributors**

---

## Who This Guide Is For

| Role | Sections to read |
|------|-----------------|
| **Organiser (Sucheta)** | Quick Start, Day-by-Day, Master Sheet, Troubleshooting |
| **Agent Owner** | Your agent's section, Configuration, Running a Single Agent |
| **Developer** | All sections + AGENT_REFERENCE.md |

---

## 1. How the System Works

```
You fill the Master Sheet row → System does everything else
```

The automation is triggered by one action: setting **Event Status = "Upcoming"** in the Master Sheet.

The Orchestrator then runs all agents in strict order:

```
Validate → Create Meetup Event → Generate QR → Create Poster → 
Approve Poster → Upload Poster → Announce → Conference Setup → 
Schedule Reminders → Event Day → Post-Event → Analytics
```

At every step, results are written back to the same row, so you always see the current status.

---

## 2. Master Sheet — Field Reference

### How to fill the sheet

1. Open the **Meetup Master Sheet**
2. Add a new row for your event
3. Fill in all **bold (required)** fields — see table below
4. Set **Event Status = "Upcoming"**
5. The automation starts within a few minutes

### Required Fields

| Section | Field | Notes |
|---------|-------|-------|
| Core | **Series** | e.g. "ML Foundations", "NLP Series" |
| Core | **Event Title** | Full event name |
| Core | **Date** | Format: `11 Oct 2025` |
| Core | **Day** | e.g. `Saturday` |
| Core | **Start Time IST** | Format: `14:00` (24h) |
| Core | **End Time IST** | Format: `17:30` |
| Core | **Mode** | `Online` / `In-Person` / `Hybrid` |
| Venue | **Venue Name** | Full building/office name |
| Venue | **Venue Address** | Full address |
| Speaker | **Speaker Name** | Full name |
| Speaker | **Highest Academic Qualification** | e.g. "PhD in CS" |
| Speaker | **Tier-1 Institution?** | `Y` or `N` |
| Speaker | **Special Achievements** | Semi-colon separated |
| Partners | **C-Level LinkedIn Handles** | Comma-separated, no @ |
| Status | **Event Status** | Set to `Upcoming` to trigger |

### Optional Fields (fill for better output)
- `Subtitle`, `Session Type`, `Google Maps URL`
- `Entrance Note`, `Parking Info`, `Laptop Required?`
- `Host Name`, `Host Phone`, `Wi-Fi Note`
- `Speaker Title`, `Speaker Org`, `Speaker LinkedIn URL`
- `Venue Sponsor Name`, `Gift Sponsor?` (Y/N)
- Promotion toggles: `LinkedIn Y/N`, `Facebook Y/N`, etc.

### Auto-filled by System
These fields are written back automatically — **do not fill manually**:
- `Meetup Event URL`, `Meetup Event ID`
- `QR Drive URL`, `Poster Drive URL`
- `Conference Link`
- All `*_Sent?` and `*_Posted?` flags

---

## 3. Day-by-Day Timeline

### At Publish (when you set Status = Upcoming)
- ✅ Meetup event created
- ✅ QR code generated
- ✅ Poster composed (draft)
- ✅ Poster sent to speakers/sponsors for approval
- *(Wait for approval — you'll get an email)*

### After Poster Approval
- ✅ Poster uploaded to Meetup
- ✅ Announcement posted: LinkedIn · Facebook · X · Instagram · Meetup Groups
- ✅ WhatsApp groups notified
- ✅ Partner outreach emails sent
- ✅ Zoom/Teams meeting created

### T-2 Days (48h before event)
- ✅ Speaker Spotlight posted on all channels + WA

### T-1 Day (24h before event)
- ✅ Logistics reminder (parking, entry, laptop, host contact) on all channels + WA

### T-2 Hours (2h before event)
- ✅ Final bump + conference link (if Online/Hybrid) on all channels + WA

### Event Day
- Run through the Conferencing Checklist (see Appendix C in blueprint)
- Ask speakers to upload materials via the Google Form link
- Verify recording/transcript/chat-saving are ON before starting

### Post-Event (within 24–48h)
1. Upload transcript to the `/04_PostEvent/03_Transcript/` Drive folder
2. Upload photos to `/04_PostEvent/01_Photos/`
3. Trigger post-event pipeline:
   ```bash
   python run.py post-event --event-id <ROW_ID>
   ```
4. System will: generate blog, post LinkedIn, share resources on Meetup + WA

---

## 4. Running the System

### Check if everything is configured
```bash
python run.py validate --config
```

### Trigger full pipeline for an event
```bash
python run.py event --event-id 2      # Row 2 in the Master Sheet
```

### Dry-run (test without real API calls)
```bash
python run.py event --event-id 2 --dry-run
```

### Check event status
```bash
python run.py status
python run.py status --event-id 2
```

### Run only one agent
```bash
python run.py event --event-id 2 --agent poster
python run.py event --event-id 2 --agent social --stage announcement
python run.py event --event-id 2 --agent reminders
```

### Trigger post-event manually
```bash
python run.py post-event --event-id 2
```

### Start the reminder scheduler
```bash
python run.py scheduler --start
python run.py scheduler --list
```

---

## 5. Agent-by-Agent Guide

### 🎯 Orchestrator
- **Owner:** Core Team
- **What it does:** Reads the sheet, validates fields, sequences all agents, writes status flags
- **When it runs:** On any row with `Event Status = Upcoming`
- **If it fails:** You'll get an email listing missing fields. Fill them and re-trigger.

### 📅 Meetup Event Agent (Neha, Atmaja)
- **What it does:** Creates/updates Meetup event, uploads poster, posts reminders to attendees
- **Setup needed:** Meetup OAuth credentials in `config/.env`
- **Run standalone:** `python run.py event --event-id X --agent meetup`

### 🔲 QR Agent (Tejal)
- **What it does:** Generates a QR code PNG for the Meetup RSVP URL
- **Output:** `QR_<EventID>.png` in Drive `/02_Output/02_QR/`
- **Run standalone:** `python run.py event --event-id X --agent qr`

### 🎨 Poster Agent (Tejal, Apeksha)
- **What it does:** Composes brand-safe poster with all required zones per Blueprint spec
- **Approval loop:** Automatically emails Drive link to speakers + sponsor. Reply APPROVED or CHANGES.
- **Run standalone:** `python run.py event --event-id X --agent poster`

### 📢 Social Syndication Agent (Ayush, Chaitanya)
- **What it does:** Posts to LinkedIn, Facebook, X, Instagram, Meetup Groups
- **4 stages:** Announcement, T-2d Spotlight, T-1d Logistics, T-2h Final Bump
- **Run standalone:** `python run.py event --event-id X --agent social --stage announcement`

### 💬 WhatsApp Helper Agent (Parth, Avishkar, Madhura, Atharva)
- **What it does:** Semi-automated posting to ~60 WA groups
- **How it works:** Opens WhatsApp Web in Chrome; you confirm Send for each group
- **First run:** Scan the QR code in Chrome to link your WhatsApp account (stored in `~/.wimlds_wa_profile`)
- **Run standalone:** `python run.py event --event-id X --agent whatsapp`

### 🤝 Partner & Media Agent (Amit Gujar)
- **What it does:** Personalized emails to partner orgs with UTM-tracked RSVP links
- **Setup:** Fill `config/partner_list.csv` with columns: `name,email,org`
- **Run standalone:** `python run.py event --event-id X --agent partner`

### 🎥 Conferencing Agent
- **What it does:** Creates Zoom/Teams/GMeet meeting with all security settings on
- **Checklist enforced:** Waiting room, cloud recording, transcription, save chat (Appendix C)
- **Note:** Uses sponsor-licensed accounts. Set ZOOM_API_KEY or TEAMS_CLIENT_ID in `.env`

### ⏰ Reminders Agent
- **What it does:** Schedules T-2d / T-1d / T-2h blasts using APScheduler + Redis
- **IST-aware:** All times calculated in Asia/Kolkata timezone
- **Idempotent:** Guards every send with flag checks — no duplicates

### 🎤 Event Execution Agent
- **What it does:** Day-of checklist + material archival
- **Manual steps:** Use the Google Form link (from `_speaker_form_url` field) to collect PPT pre-event

### ✍️ Post-Event Agent
- **What it does:** Transcript → LLM blog → LinkedIn → Meetup resources → WA closed sharing
- **Closed sharing rule strictly enforced:** Recording/Transcript/Slides NEVER on public social
- **Trigger:** `python run.py post-event --event-id X`

### 📊 Analytics Agent
- **What it does:** Aggregates KPIs, updates Looker Studio / Metabase, sends completion email
- **Dashboard:** Auto-refreshes from connected Google Sheet

---

## 6. Poster Approval Workflow

1. Poster is created and uploaded to Drive
2. An email is sent to: Speaker, Venue Sponsor, and you (organizer)
3. Reply **"APPROVED"** to proceed
4. Reply **"CHANGES: [your notes]"** to trigger a rework
5. After approval, poster is automatically uploaded to the Meetup event

**If approval email is not received:** Check your spam, or run:
```bash
python run.py event --event-id X --agent poster --stage send_approval
```

---

## 7. WhatsApp Setup (First Time)

1. Make sure Chrome is installed on the system running the automation
2. Run any WA send command — Chrome will open `web.whatsapp.com`
3. Scan the QR code with your WhatsApp mobile app
4. Your session is saved in `~/.wimlds_wa_profile` — you won't need to scan again

**Policy compliance:** The agent pauses at each group and requires you to type `y` to confirm. It never bulk-sends without human oversight.

---

## 8. Closed Sharing Policy

> 🔒 Recording, Transcript, and Slides are **NEVER** posted on public social media.

| Channel | Gets public content | Gets recording/slides |
|---------|--------------------|-----------------------|
| LinkedIn | ✅ | ❌ |
| Facebook | ✅ | ❌ |
| X / Twitter | ✅ | ❌ |
| Instagram | ✅ | ❌ |
| Meetup (Attendees) | ✅ | ✅ |
| WhatsApp Groups (closed) | ✅ | ✅ |
| Individual WA | ❌ | ❌ |

---

## 9. Troubleshooting

| Problem | Solution |
|---------|----------|
| "Missing fields" email received | Fill the listed fields in the Master Sheet |
| Poster approval stuck | Re-send with `--agent poster --stage send_approval` |
| Social post fails | Check token expiry. Refresh LinkedIn/FB tokens in `.env` |
| WA Chrome won't open | Check Chrome is installed: `which google-chrome` |
| Reminders not firing | Check Redis: `redis-cli ping`. Check scheduler: `python run.py scheduler --list` |
| Zoom creation fails | Verify Zoom JWT credentials in `.env` |
| LLM blog generation fails | Check `ANTHROPIC_API_KEY` or switch `LLM_PROVIDER=openai` |
| "Service account not found" | Place `service-account.json` in `config/` folder |

---

## 10. Security Reminders

- ❌ Never commit `config/.env` to git (pre-commit hook blocks this)
- 🔄 Rotate OAuth tokens every ~60 days using `python scripts/rotate_tokens.py`
- 🔐 Enable 2FA on your primary Meetup organizer account
- 👀 Review `docs/SECURITY.md` for the full security policy

---

## 11. Naming Conventions (Appendix D)

| Asset | Convention |
|-------|-----------|
| Event folder | `YYYY-MM-DD_<Series>_<ShortTitle>` |
| Poster | `Poster_Final.png` |
| QR Code | `QR_<EventID>.png` |
| Transcript | `YYYY-MM-DD_<Series>_Transcript.txt` |
| Recording | `YYYY-MM-DD_<Series>_Recording.mp4` |
| Slides | `YYYY-MM-DD_<Series>_<SpeakerLastName>.pdf` |

---

*Questions? Contact the Core Team or raise an issue in the repository.*
