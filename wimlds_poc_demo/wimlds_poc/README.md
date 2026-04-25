# WiMLDS Pune — Zero-Credential POC Demo

Run the complete 12-stage automation pipeline **without any API keys**.  
All external calls are mocked with realistic output. Works on Windows / Mac / Linux.

---

## 1 — Install (one time)

```bash
cd wimlds_poc
pip install -r requirements_poc.txt
```

That's it. No `.env`, no Google account, no Redis, no Meetup credentials.

---

## 2 — Run the full pipeline

```bash
python demo.py
```

Runs all 12 stages end-to-end and writes output files to `output/`.

---

## 3 — Useful single commands

| Command | What it does |
|---------|--------------|
| `python demo.py` | Full 12-stage pipeline |
| `python demo.py --agent poster` | Poster agent only |
| `python demo.py --agent social --stage announcement` | Announcement blast |
| `python demo.py --agent social --stage t2d` | T-2d Speaker Spotlight |
| `python demo.py --agent social --stage t1d` | T-1d Logistics reminder |
| `python demo.py --agent social --stage t2h` | T-2h Final Bump |
| `python demo.py --agent conferencing` | Create Zoom (mocked) |
| `python demo.py --remind t2d` | Simulate reminder firing |
| `python demo.py --post-event` | Post-event pipeline + analytics |
| `python demo.py --show-output` | Print what was written back to sheet |
| `python demo.py --reset` | Clear state → run demo fresh again |

---

## 4 — Output files generated

| File | Contents |
|------|----------|
| `output/QR_demo.png` | Real QR code PNG (purple, WiMLDS branded) |
| `output/Poster_Final_demo.png` | Real poster image (1080×1350) |
| `output/social_announcement.txt` | Announcement social copy |
| `output/social_t2d.txt` | T-2d Speaker Spotlight copy |
| `output/social_t1d.txt` | T-1d Logistics copy |
| `output/social_t2h.txt` | T-2h Final Bump copy |
| `output/linkedin_post.txt` | Post-event LinkedIn gratitude post |
| `output/blog_draft.md` | LLM-generated blog draft |
| `output/kpi_report.json` | Event KPI aggregation |
| `output/event_state.json` | All fields written back to sheet |
| `logs/demo.log` | Full execution log |

---

## 5 — What's mocked vs real

| Component | In POC | In Production |
|-----------|--------|---------------|
| Data source | `config/event_data.json` | Google Sheets (MCP) |
| State store | `output/event_state.json` | Redis + Sheets write-back |
| Meetup API | Mock response with fake IDs | OAuth 2.0 REST API |
| Social APIs | Mock post IDs | LinkedIn / FB / X / IG APIs |
| QR code | **Real PNG generated** | Same |
| Poster image | **Real PNG generated** | Same + Drive upload |
| WhatsApp | Mock per-group send | Selenium + WhatsApp Web |
| Zoom/Teams | Mock meeting ID + link | Zoom JWT / MS Graph API |
| Email | Mock SendGrid 202 | Real SendGrid delivery |
| LLM blog | Template blog (realistic) | Claude / GPT API |
| APScheduler | Jobs registered (no firing) | Redis-backed persistent jobs |
| Analytics | Randomised realistic KPIs | Live Meetup + social API data |

---

## 6 — Connecting real credentials later

When you have the API keys, point `demo.py` at `run.py` from the main repo:

```bash
# In the main repo (with real credentials in config/.env)
python run.py event --event-id 3 --dry-run   # dry run (no real posts)
python run.py event --event-id 3             # go live
```

The POC and main repo share the same 12-stage structure, agent names,
and sheet field names — so the transition is seamless.
