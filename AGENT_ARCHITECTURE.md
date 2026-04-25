# Poster Agent - Complete Architecture & Workflow Documentation

## Overview

**Poster Agent** is a fully automated event poster generation system that:
1. Reads event data from a Google Sheet (Meetup Planning Sheet)
2. Downloads assets (backgrounds, fonts, speaker photos) from Google Drive
3. Generates professional event posters in multiple variants (1, 2, 3 speakers × online/offline modes)
4. Saves posters locally and uploads them back to Google Drive

The system is designed for **team collaboration** using a shared community Google account and OAuth authentication.

---

## System Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINT (main)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│         Initialize Google Drive Manager (OAuth)             │
│   - Load/refresh authentication tokens                      │
│   - Resolve folder structure in Drive                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│    check_and_generate() — Main Automation Loop              │
│   - Download Excel sheet from Drive                         │
│   - Filter for upcoming events                              │
│   - Input filters: Status="Upcoming" + No. of Speakers + Mode
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│   For Each Matching Event:                                  │
│   - Download offline background for speaker variant         │
│   - Generate poster using generate_offline_poster()         │
│   - Save locally to posters_output/[speaker_count]/         │
│   - (Optional) Upload to Google Drive                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│    Loop Control (Monitoring Mode)                           │
│   - Wait 1 minute (configurable)                            │
│   - Check for new events again                              │
│   - Ctrl+C to stop                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. **poster_agent.py** — Main Agent

**Purpose:** Orchestrates the entire poster generation workflow

**Key Functions:**

#### `main()`
- Initializes Google Drive Manager
- Starts monitoring loop (checks every 1 minute by default)
- Handles Ctrl+C for graceful shutdown

#### `check_and_generate(drive: GoogleDriveManager)`
- Downloads latest Excel sheet from Google Drive
- **Validates required columns**: Status, No. of Speakers, Mode
- **Filters events**:
  - Status = "Upcoming" (case-insensitive)
  - No. of Speakers ∈ [1, 2, 3]
  - Mode ∈ ["Offline", "offline"]
- **Current focus**: Generates only **one-speaker offline** posters
  - Reads: `No. of Speakers = "1"` AND `Mode = "offline"`
  - Future: Will support two-speaker and three-speaker variants
- Downloads offline backgrounds for each speaker variant
- Calls `generate_offline_poster()` for each event
- Saves posters locally to `posters_output/one_speaker/` folder

#### `generate_offline_poster(row, drive, background_path, font_path, platform)`
- **Inputs:**
  - `row`: DataFrame row with event data
  - `drive`: GoogleDriveManager instance
  - `background_path`: Path to offline background image (2000×1414px)
  - `font_path`: Path to Helvetica-Bold.ttf
  - `platform`: Platform type (e.g., "offline_one" for one speaker)

- **Poster elements drawn** (in order):
  1. **QR Code** — Links to Meetup event
  2. **Title** — Event title (centered, white text)
  3. **Date/Day** — Right-aligned with time
  4. **Time** — Right-aligned
  5. **Speaker Photos** — Rounded corners, portrait aspect ratio
  6. **Speaker Info** — Name + Role/Company (white text)
  7. **Venue Info** — Venue name and address (right-aligned)
  8. **Sponsor Logos** — Community partners & gift sponsors (auto-scaling)

- **Output:** Local file path to generated poster PNG

### 2. **gdrive_manager.py** — Reusable Google Drive Module

**Purpose:** Provides team-wide Google Drive operations abstraction

**Key Methods:**

```python
drive = GoogleDriveManager()  # Handles OAuth automatically

# File operations
file_id = drive.find_file(name, parent_folder_id)
folder_id = drive.find_folder(name, parent_folder_id)
success = drive.download_file(file_id, save_path)
uploaded_id = drive.upload_file(local_path, folder_id, replace_existing=True)

# Folder management
folder_id = drive.create_folder(name, parent_folder_id)
folder_id = drive.get_or_create_folder(name, parent_folder_id)
```

**Authentication Flow:**
1. Check for existing `token.json` → use cached token
2. If token expired → refresh with refresh token
3. If no token → OAuth browser login (first run only)
4. Save token for future runs

**Error Handling:** All methods return `None`/`False` on failure (never crashes)

---

## Configuration System

### Excel Sheet Structure (Meetup Planning Sheet.xlsx)

| Column | Values | Purpose |
|--------|--------|---------|
| **Status** | "Upcoming", "Past", etc. | Filter for upcoming events |
| **No. of Speakers** | 1, 2, or 3 | Determines poster variant |
| **Mode** | "Online" / "Offline" | Determines background template used |
| Date | YYYY-MM-DD | Event date |
| Time | HH:MM | Event time |
| Title | Text | Event title |
| Day | Text (e.g., "Tuesday") | Day of week |
| Venue Address | Text | Venue location |
| Meetup link for Title/Sub Title/QR Code | URL | QR code destination |
| Speaker1 | Name | Primary speaker |
| Speaker | Role | Primary speaker role/company |
| Speaker1_Company | Company | Company name |
| Speaker1_Photo | Drive link or URL | Speaker photo |
| speakers | Name | Second speaker (column reused) |
| Speaker2_Role | Role | Second speaker role |
| Speaker2_Company | Company | Company name |
| Speaker2_Photo | Drive link | Speaker photo |
| Speaker3, Speaker3_Role, Speaker3_Company, Speaker3_Photo | ... | Third speaker info |
| Community Partners | Name | Community partner name |
| Gift Sponsor | Name | Gift sponsor name |

### Google Drive Folder Structure

```
Poster Automation/
├── Meetup Planning Sheet.xlsx          # Event data (read every cycle)
├── Speaker Photos/                      # Speaker photo pool
├── Helvetica-Bold.ttf                  # Font file
├── One Speaker/
│   └── Offline Background.png           # 2000×1414px background (one speaker)
├── Two Speakers/
│   └── Offline Background.png           # 2000×1414px background (two speakers)
├── Three Speakers/
│   └── Offline Background.png           # 2000×1414px background (three speakers)
└── Community Partners and Gift Sponsors/
    └── [Logo files by name]             # Sponsor logos
```

### Layout Configuration (Dimensions in Millimeters)

**Scale Factor:** 6.734 pixels per millimeter (for 2000×1414px A4 landscape)

**For One Speaker:**
```python
{
    "qr": {"x": 5.83, "y": 16.23, "w": 39.79, "h": 39.35},
    "title": {"x": 45.04, "y": 24.43, "w": 200.08, "h": 26.56, "size": 30},
    "day_date": {"x": 178.32, "y": 97.63, "w": 111.43, "h": 9.06, "size": 21},
    "time": {"x": 175.51, "y": 109.6, "w": 116.17, "h": 9.06, "size": 21},
    "photos": [
        {"x": 10.28, "y": 114.91, "w": 38.57, "h": 39.57}
    ],
    "speakers": [
        {"x": 52.35, "y": 126.6, "w": 107.04, "h": 16.19, "name_size": 14, "role_size": 13}
    ],
    "venue_address": {"x": 164.37, "y": 148.21, "w": 123.39, "h": 26.16, "name_size": 20, "addr_size": 19}
}
```

**Font Sizes:** All in pixel values (configured per element)
- Title: **30px** (Helvetica-Bold)
- Speaker Name: **14px** (Arial Bold)
- Speaker Role: **13px** (Arial Bold)
- Date/Time: **21px** (Calibri)
- Venue: **20px name**, **19px address** (Calibri)

**Text Alignment:**
- Title: **Centered** within width boundary
- Date/Time/Venue: **Right-aligned**
- Speaker info: **Left-aligned**

---

## Authentication System

### Team-Based Setup

All team members use a **single shared community Google account**:

1. **Google Cloud Console**
   - Project: "Event Agent" (event-agent-489509)
   - OAuth Client: Desktop Application
   - Service Account: poster-agent@event-agent-489509.iam.gserviceaccount.com

2. **Authentication Files** (NEVER commit to Git)
   - `credentials.json` — OAuth client credentials
   - `token.json` — Auto-generated after first login (refresh token)
   - `event-agent-489509-b7264d4ca861.json` — Service account key

3. **First Run**
   - Browser opens automatically
   - Sign in with community Google account
   - Click "Allow" for Drive access
   - System saves token for future runs

4. **Subsequent Runs**
   - System auto-refreshes token (no browser needed)
   - Works for all team members using same community account

### SCOPES (Permissions)

```python
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # Access to created/shared files
    "https://www.googleapis.com/auth/drive"        # Full Drive access
]
```

---

## File Generation & Output

### Local Output Directory Structure

```
posters_output/
└── one_speaker/
    ├── 2024-03-15_Event_Title_one_speaker_offline.png
    ├── 2024-03-20_Next_Event_one_speaker_offline.png
    └── ...

(Future)
├── two_speakers/
│   └── ...
└── three_speakers/
    └── ...
```

### Poster Filename Convention

```
{DATE}_{TITLE}_{VARIANT}_{MODE}.png

Example: 2024-03-15_Python_Meetup_one_speaker_offline.png
```

### Image Generation Process

1. **Load Background** (2000×1414px from Drive)
2. **Create Canvas** (PIL Image object, RGB mode)
3. **Draw Elements** (in order, using ImageDraw):
   - Paste QR code image
   - Draw text with specific fonts
   - Paste and crop speaker photos
   - Scale and paste sponsor logos
4. **Save to Disk** (PNG format, full quality)

---

## Event Filtering Logic

**Current Implementation (One-Speaker Offline Only):**

```python
# Step 1: Load Excel and validate columns
upcoming = df[df[COL_STATUS].str.lower() == "upcoming"]

# Step 2: Filter for one-speaker offline ONLY
one_speaker_offline = upcoming[
    (upcoming[COL_NUM_SPEAKERS].astype(str).str.strip() == "1") &
    (upcoming[COL_MODE].astype(str).str.lower().isin(["offline"]))
]

# Step 3: For each matching event, generate poster
for _, row in one_speaker_offline.iterrows():
    generate_offline_poster(row, drive, bg_path, font_path, platform="offline_one")
```

**Future Expansion (Multi-Variant):**

Once one-speaker is tested and verified:
```python
# Generate based on No. of Speakers column
for num_speakers in [1, 2, 3]:
    for mode in ["offline"]:  # or ["online"] for online variants
        filtered = upcoming[
            (upcoming[COL_NUM_SPEAKERS] == num_speakers) &
            (upcoming[COL_MODE].str.lower() == mode)
        ]
        # Generate and save to appropriate folder
```

---

## Key Constants & Configuration

### In poster_agent.py

```python
# Google Drive Folders
GDRIVE_BASE_FOLDER = "Poster Automation"
OFFLINE_ONE_SPEAKER_FOLDER = "One Speaker"
OFFLINE_TWO_SPEAKERS_FOLDER = "Two Speakers"
OFFLINE_THREE_SPEAKERS_FOLDER = "Three Speakers"

# Files
EXCEL_FILENAME = "Meetup Planning Sheet.xlsx"
OFFLINE_BACKGROUND_FILENAME = "Offline Background.png"
FONT_FILENAME = "Helvetica-Bold.ttf"

# Fonts
NAME_ROLE_FONT = "C:/Windows/Fonts/arialbd.ttf"       # Arial Bold
DATE_MODE_FONT = "C:/Windows/Fonts/calibri.ttf"       # Calibri

# Output
OUTPUT_LOCAL_FOLDER = "posters_output"
OUTPUT_ONE_SPEAKER = "posters_output/one_speaker"
TEMP_FOLDER = "temp_downloads"

# Monitoring
CHECK_INTERVAL = 1 * 60  # 1 minute (testing); change to 30*60 for production

# Track generated posters (prevent duplicates in same session)
generated_posters: set = set()
```

---

## Conversion: MM to Pixels

**Formula:** `pixels = millimeters × 6.734`

This conversion applies for a 2000×1414px A4 landscape layout:
- A4 Width: 210mm → 2000px ÷ 210 ≈ 9.52px/mm (not used)
- **Used scale: 6.734px/mm** (optimized for visual design)

**Examples:**
```
5.83 mm = 39.27 px  (QR position X)
39.79 mm = 267.78px (QR width)
30 px = font size (already in pixels, not converted)
```

---

## Error Handling & Recovery

### Network Errors
- Retry up to 3 times with 30-second delays
- Print warning on failure
- Continue to next cycle

### Missing Files
- QR link missing → Skip QR code
- Speaker photo missing → Skip photo for that speaker
- Sponsor logo missing → Skip that logo
- Background missing → Skip entire poster generation

### Excel Parse Errors
- Invalid date format → Use raw string
- Missing column → Print error, skip event
- Empty value → Use None, skip that element

### OAuth Token Errors
- Expired token → Auto-refresh
- Revoked token → Re-prompt browser login
- Missing credentials.json → Print error, exit

---

## Performance & Scalability

### Current Performance
- **Event Processing Time:** ~5-10 seconds per poster
- **Check Interval:** 1 minute (testing), 30 minutes (production)
- **Memory Usage:** ~50-100 MB (PIL image operations)

### Scaling Considerations
- **Multiple Events:** Processes sequentially (can be parallelized)
- **Multiple Speakers:** Supports 1, 2, or 3 (layout configs provided)
- **Batch Operations:** Can generate all variants in one run
- **Rate Limits:** Google Drive API has quota limits (~10K requests/day)

---

## Testing & Debugging

### Manual Test Commands

```bash
# Test Excel read
python -c "import pandas as pd; df = pd.read_excel('temp_downloads/Meetup Planning Sheet.xlsx'); print(df.columns.tolist())"

# Test Drive auth
python -c "from gdrive_manager import GoogleDriveManager; d = GoogleDriveManager(); print(d.find_folder('Poster Automation'))"

# Test poster generation
python poster_agent.py  # Runs once, then enters monitoring loop

# Run in background (Linux/Mac)
python poster_agent.py > poster_agent.log 2>&1 &
```

### Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| "No upcoming events" | No events match filter | Check Excel Status, No. of Speakers, Mode columns |
| "OAuth token expired" | Token needs refresh | Delete token.json, re-authenticate |
| "Background not found" | Missing offline background in Drive | Upload "Offline Background.png" to One/Two/Three Speaker folders |
| "Module not found" | Missing gdrive_manager.py | Ensure gdrive_manager.py is in same folder as poster_agent.py |
| Slow poster generation | Network latency | Check internet connection, reduce CHECK_INTERVAL |

---

## Future Enhancements

### Phase 1 (Current)
✅ One-speaker offline poster generation
✅ Excel filtering (Status, No. of Speakers, Mode)
✅ Google Drive integration
✅ Local output with organized folder structure

### Phase 2 (Planned)
- [ ] Two-speaker and three-speaker variant generation
- [ ] Online mode poster generation
- [ ] Batch processing (generate all variants in one run)
- [ ] Parallel poster generation (faster processing)
- [ ] Email notifications (when new posters generated)

### Phase 3 (Future)
- [ ] Poster templates library (multiple design options)
- [ ] Custom font selection per event
- [ ] Real-time poster preview in browser
- [ ] Analytics dashboard (posters generated, events processed)

---

## Team Collaboration Guidelines

### For New Team Members

1. **Clone Repository**
   ```bash
   git clone <repo-url>
   cd poster-agent
   ```

2. **Get Authentication Files** (from team lead)
   - `credentials.json`
   - `event-agent-489509-b7264d4ca861.json`

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **First Run** (will prompt browser login)
   ```bash
   python poster_agent.py
   # Once authenticated, token.json is auto-generated (don't commit!)
   ```

5. **Update .gitignore** (sensitive files)
   ```
   credentials.json
   token.json
   event-agent-*.json
   ```

### Code Review Checklist

- [ ] Changes to layout dimensions documented
- [ ] New Excel columns added (update COL_* constants)
- [ ] Authentication files NOT committed
- [ ] Error handling added for new features
- [ ] Tested with actual Excel data before merge

---

## Summary

**Poster Agent** is a sophisticated automation system that combines:
1. **Data Pipeline** — Excel → Google Sheets → Event Filtering
2. **Asset Management** — Google Drive integration for backgrounds, photos, logos
3. **Image Generation** — PIL-based poster creation with precise MM-based layouts
4. **Team Collaboration** — Shared OAuth authentication, modular code structure
5. **Monitoring** — Continuous checking for new events with error recovery

The architecture is designed to be **scalable**, **maintainable**, and **team-friendly**.

