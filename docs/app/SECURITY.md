# 🔐 Security Policy

## Credentials
- All API keys stored in `config/.env` — never committed to git
- Pre-commit hook blocks accidental `.env` commits
- Rotate OAuth tokens every ~60 days: `python scripts/rotate_tokens.py`
- 2FA enforced on primary Meetup organizer account
- Google Service Account: Editor on Sheet + Drive only (minimum required)

## WhatsApp
- Semi-manual confirm-per-send (policy-safe; no bulk automation)
- Session stored locally in `~/.wimlds_wa_profile`

## Closed Sharing
- Recording/Transcript/Slides: NEVER on public social media
- Enforced in code: `post_event_agent.py` never passes these URLs to social platforms
- Shared only via: Meetup attendee message + closed WA groups

## Missing Fields
- No downstream job runs until all required fields are present
- Owner auto-notified by email with exact missing field list
