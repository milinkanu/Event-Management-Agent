# Poster Agent

Poster Agent generates event posters from a shared Google Drive workspace.
It reads the latest event data from the planning sheet, downloads templates,
backgrounds, speaker photos, and sponsor assets from Drive, generates posters
locally, and uploads the final output back to Drive.

Current scope:
- General posters for `1`, `2`, and `3` speaker variants
- `Online` and `Offline` poster modes
- Shared Google Drive based workflow
- Shared logging and shared auth/config constants

## Main Files

- `poster_agent.py`
  Main poster generation workflow
- `gdrive_manager.py`
  Shared Google Drive integration layer
- `auth_runner.py`
  Small auth bootstrap script for OAuth setup
- `app_constants.py`
  Shared auth/config filenames
- `app_logging.py`
  Common logging setup for the full app

## Drive Structure

The project expects a top-level Drive folder named `Poster Automation`.

### Source folders

```text
Poster Automation/
  Meetup Planning Sheet.xlsx
  Community Partners/
  Gift Sponsors/
  Speaker Photos/
  Venue Sponsors/
  Templates/
    One Speaker/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
    Two Speakers/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
    Three Speakers/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
```

### Generated output folders

```text
Poster Automation/
  Generated Posters/
    1 Speaker/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
    2 Speakers/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
    3 Speakers/
      Online/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
      Offline/
        General/
        Instagram/
        Facebook/
        Twitter/
        LinkedIn/
```

At present, the implemented upload path is the `General` folder for each
speaker-count and mode combination.

## Authentication

This project uses a shared community Google account model.

Required local files:
- `credentials.json`
- `token.json`
- `event-agent-489509-b7264d4ca861.json`

These filenames are defined centrally in `app_constants.py`.

### First-time auth

Run:

```bash
python auth_runner.py
```

This starts the OAuth flow and opens the browser for sign-in. Use the shared
community Google account, not a personal account.

## Logging

The entire app uses common logging through `app_logging.py`.

Modules using the shared logger:
- `auth_runner.py`
- `poster_agent.py`
- `gdrive_manager.py`

This keeps logs consistent across authentication, Drive access, and poster
generation.

## Setup

1. Install Python `3.8+`
2. Install dependencies
3. Place auth files in the project root
4. Ensure the `Poster Automation` Drive folder is shared correctly

Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Agent

### Continuous mode

```bash
python poster_agent.py
```

Current polling interval:
- every `1 hour`

### Test mode

```bash
python test_generate.py
```

## Poster Selection Logic

The agent reads the planning sheet and only processes rows that match:

- `Status = Upcoming` (case-insensitive)
- `No. of Speakers = 1, 2, or 3`
- `Mode = Online or Offline` (case-insensitive)

The current generation flow produces general posters and uploads them to:

```text
Generated Posters/<speaker>/<mode>/General/
```

## Local Working Folders

These are runtime folders and should not be committed:

- `temp_downloads/`
- `posters_output/`
- `__pycache__/`

## Files That Must Not Be Committed

- `credentials.json`
- `token.json`
- `event-agent-*.json`
- generated outputs
- temporary downloads
- log files

## Notes for Team Integration

This codebase is a good fit for later orchestration work because the logic is
already separated into:
- authentication
- Drive access
- poster generation
- shared config
- shared logging

Planned but not finalized yet:
- LangGraph or orchestrator-based triggering
- platform-specific poster generation flow
- webhook/event-driven execution from sheet updates

## Troubleshooting

### OAuth fails

Delete `token.json` and run:

```bash
python auth_runner.py
```

Then sign in again with the shared community Google account.

### Drive folder not found

Check that:
- the `Poster Automation` folder exists
- the folder names match expected values
- the shared account has the required permissions

### Poster not generated

Check that the row in the planning sheet is:
- marked `Upcoming`
- has a valid speaker count
- has a valid mode
- has the required source assets in Drive

## Current Status

Implemented:
- General online posters
- General offline posters
- Shared Drive upload flow
- Shared logging
- Shared auth constants

Deferred for now:
- MP4 output
- platform-specific poster generation
- orchestration trigger refactor
