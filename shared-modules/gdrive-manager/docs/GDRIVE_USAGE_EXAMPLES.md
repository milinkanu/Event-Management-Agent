# Google Drive Manager — Usage Examples for Other Agents

This document shows how to use the reusable `gdrive_manager.py` module in other automation agents.

---

## Quick Start

```python
from gdrive_manager import GoogleDriveManager

# Initialize (handles authentication automatically)
drive = GoogleDriveManager()

# Upload a file
file_id = drive.upload_file("report.pdf", folder_id="abc123...")

# Download a file
drive.download_file(file_id="xyz789...", save_path="downloaded.pdf")
```

On first run, a browser opens for OAuth — sign in with the **community Google account**. Subsequent runs use the saved token automatically.

---

## Example 1: Email Agent — Sending Attachments

```python
"""
Email Agent — Downloads files from Drive and sends them via email
"""
from gdrive_manager import GoogleDriveManager
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Initialize Drive manager
drive = GoogleDriveManager()

# Find the reports folder
reports_folder_id = drive.find_folder("Monthly Reports")

# List all PDF reports
pdf_files = drive.list_files(
    folder_id=reports_folder_id,
    file_type="application/pdf",
    max_results=10
)

# Download each report
for file_info in pdf_files:
    file_id = file_info['id']
    filename = file_info['name']
    local_path = f"temp/{filename}"

    print(f"Downloading {filename}...")
    if drive.download_file(file_id, local_path):
        # Send via email
        send_email_with_attachment(
            to="team@company.com",
            subject=f"Report: {filename}",
            attachment=local_path
        )
        print(f"✓ Sent {filename}")
```

---

## Example 2: Social Media Agent — Uploading Generated Content

```python
"""
Social Media Agent — Generates graphics and uploads to Drive for review
"""
from gdrive_manager import GoogleDriveManager
from PIL import Image, ImageDraw, ImageFont

# Initialize
drive = GoogleDriveManager()

# Find or create output folder
output_folder_id = drive.get_or_create_folder(
    folder_name="Social Media Posts",
    parent_id=None  # root folder
)

# Generate a social media graphic
def create_post_image(text):
    img = Image.new('RGB', (1080, 1080), color='white')
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 48)
    draw.text((100, 500), text, fill='black', font=font)
    img.save("temp_post.jpg")
    return "temp_post.jpg"

# Create and upload
post_file = create_post_image("New Product Launch!")
file_id = drive.upload_file(
    local_path=post_file,
    folder_id=output_folder_id,
    custom_name="product_launch_post.jpg",
    replace_existing=True
)

print(f"✓ Uploaded social media post (file_id: {file_id})")
```

---

## Example 3: Analytics Agent — Processing Data Files

```python
"""
Analytics Agent — Downloads CSV data, processes it, uploads results
"""
from gdrive_manager import GoogleDriveManager
import pandas as pd

# Initialize
drive = GoogleDriveManager()

# Find data folder
data_folder_id = drive.find_folder("Raw Data")

# List all CSV files
csv_files = drive.list_files(
    folder_id=data_folder_id,
    file_type="text/csv"
)

for file_info in csv_files:
    filename = file_info['name']
    print(f"Processing {filename}...")

    # Download
    local_csv = f"temp/{filename}"
    if drive.download_file(file_info['id'], local_csv):

        # Process data
        df = pd.read_excel(local_csv)
        summary = df.describe()

        # Save summary
        summary_file = f"temp/summary_{filename}"
        summary.to_csv(summary_file)

        # Upload results
        results_folder_id = drive.get_or_create_folder(
            "Processed Data",
            parent_id=data_folder_id
        )

        drive.upload_file(
            local_path=summary_file,
            folder_id=results_folder_id
        )

        print(f"✓ Processed and uploaded summary for {filename}")
```

---

## Example 4: Backup Agent — Archiving Files

```python
"""
Backup Agent — Creates backup copies of important files
"""
from gdrive_manager import GoogleDriveManager
from datetime import datetime

# Initialize
drive = GoogleDriveManager()

# Find important folders to backup
source_folder_id = drive.find_folder("Project Files")

# Create timestamped backup folder
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_folder_id = drive.create_folder(
    folder_name=f"Backup_{timestamp}",
    parent_id=None
)

# List all files
files = drive.list_files(source_folder_id, max_results=100)

# Copy each file
for file_info in files:
    file_id = file_info['id']
    filename = file_info['name']

    # Download
    temp_path = f"temp/{filename}"
    if drive.download_file(file_id, temp_path):

        # Re-upload to backup folder
        drive.upload_file(
            local_path=temp_path,
            folder_id=backup_folder_id
        )

        print(f"✓ Backed up {filename}")

print(f"✓ Backup complete! Folder ID: {backup_folder_id}")
```

---

## Example 5: Simple Task — One-liner Operations

```python
from gdrive_manager import quick_upload, quick_download

# Upload a file (one line)
file_id = quick_upload("document.pdf", "folder_abc123")

# Download a file (one line)
quick_download("file_xyz789", "downloaded.pdf")
```

---

## Error Handling Best Practices

```python
from gdrive_manager import GoogleDriveManager, DriveAuthenticationError

try:
    # Initialize
    drive = GoogleDriveManager()

    # Try to upload
    file_id = drive.upload_file("report.pdf", "abc123")

    if file_id:
        print(f"✓ Success! File ID: {file_id}")
    else:
        print("✗ Upload failed (see error messages above)")

except DriveAuthenticationError as exc:
    print(f"Authentication failed: {exc}")
    print("Check that credentials.json exists and is valid")

except Exception as exc:
    print(f"Unexpected error: {exc}")
```

---

## Common Patterns

### Pattern 1: Find or Create Workflow

```python
# Always use get_or_create to avoid duplicates
folder_id = drive.get_or_create_folder("Output", parent_id)
```

### Pattern 2: Replace Existing Files

```python
# Set replace_existing=True to update files with same name
drive.upload_file(
    local_path="report.pdf",
    folder_id=folder_id,
    replace_existing=True  # ← Updates if exists, creates if new
)
```

### Pattern 3: Batch Processing

```python
# List files, then process each
files = drive.list_files(folder_id, max_results=50)

for file_info in files:
    process_file(file_info['id'], file_info['name'])
```

---

## Authentication Flow (Automatic)

**First run:**
```
→ Opening browser for Google sign-in...
⚠️  IMPORTANT: Sign in with the COMMUNITY Google account
✓ OAuth authenticated and token saved to token.json
✓ Future runs will use saved token (no browser required)
```

**Subsequent runs:**
```
✓ Loaded OAuth token from token.json
✓ Google Drive service ready (OAuth)
```

**Token expired:**
```
→ Refreshing expired OAuth token...
✓ Token refreshed and saved to token.json
```

---

## Module API Reference

### Initialization

```python
GoogleDriveManager(
    credentials_file="credentials.json",
    token_file="token.json",
    service_account_file=None,
    use_service_account=False
)
```

### File Operations

```python
# Upload
file_id = drive.upload_file(local_path, folder_id, custom_name=None,
                             replace_existing=True, mime_type=None)

# Download
success = drive.download_file(file_id=None, save_path=None,
                               file_name=None, folder_id=None)

# Delete
success = drive.delete_file(file_id)
```

### Folder Operations

```python
# Create
folder_id = drive.create_folder(folder_name, parent_id=None)

# Find or create
folder_id = drive.get_or_create_folder(folder_name, parent_id=None)
```

### Search Operations

```python
# Find file
file_id = drive.find_file(file_name, folder_id=None)

# Find folder
folder_id = drive.find_folder(folder_name, parent_id=None)

# List files
files = drive.list_files(folder_id=None, max_results=100, file_type=None)
```

---

## Team Guidelines

### ⚠️ Authentication

- **ALWAYS** use the community Google account for OAuth
- **NEVER** commit `credentials.json` or `token.json` to Git
- Each team member generates their own `token.json` on first run

### ⚠️ Credentials Sharing

Share securely via:
- Password manager (1Password, Bitwarden)
- Encrypted cloud storage
- Secure messaging (Signal)

**DO NOT** share via:
- Git repositories
- Plain text email
- Unencrypted chat

### ⚠️ Error Handling

- Methods return `None` or `False` on failure (never crash)
- Error messages are printed automatically
- Always check return values before proceeding

---

## Troubleshooting

### "OAuth authentication failed"

**Cause:** Wrong Google account used during login

**Fix:**
1. Delete `token.json`
2. Run agent again
3. Sign in with **community account** (not personal)

---

### "Permission denied"

**Cause:** File/folder not shared with your account

**Fix:**
- Ensure folder is shared with community Google account
- Check "Editor" permissions are granted

---

### "Quota exceeded"

**Cause:** Drive storage is full

**Fix:**
- Free up space in Google Drive
- Upgrade storage plan
- Delete old files

---

## Next Steps

1. Copy `gdrive_manager.py` to your agent's project folder
2. Install requirements: `pip install google-auth google-auth-oauthlib google-api-python-client`
3. Add authentication files to `.gitignore`
4. Initialize Drive manager in your agent code

**The module is ready for use across all automation agents!** 🎉
