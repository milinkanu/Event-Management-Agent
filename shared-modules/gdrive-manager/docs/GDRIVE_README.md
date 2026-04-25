# Google Drive Manager — Quick Setup Guide

A reusable Python module for Google Drive operations used across all automation agents in our community.

---

## 🎯 What This Module Does

- ✅ Upload files to Google Drive
- ✅ Download files from Google Drive
- ✅ List, search, and organize files/folders
- ✅ Automatic OAuth authentication (one-time browser login)
- ✅ Team-based access (single community Google account)
- ✅ Comprehensive error handling

**Perfect for:** Poster Agent, Email Agent, Social Media Agent, Analytics Agent, and any future automation tools.

---

## 📋 Prerequisites

1. **Python 3.7+** installed
2. **Google Cloud Project** with Drive API enabled
3. **OAuth credentials** (`credentials.json`) — get from project admin
4. **Community Google account** credentials for authentication

---

## 🚀 Setup Instructions (Step-by-Step)

### Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd "Poster Agent"
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `google-auth`
- `google-auth-oauthlib`
- `google-auth-httplib2`
- `google-api-python-client`

### Step 3: Get OAuth Credentials

**Option A: Get from Team Admin**
- Ask your project admin for `credentials.json`
- Place it in the project root folder

**Option B: Create New Credentials (Admin Only)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project → "APIs & Services" → "Credentials"
3. Click "Create Credentials" → "OAuth 2.0 Client ID"
4. Application type: "Desktop app"
5. Download JSON → rename to `credentials.json`
6. Place in project root

### Step 4: First Run Authentication

```bash
python gdrive_manager.py
```

**What happens:**
1. Browser opens automatically
2. Sign in with **COMMUNITY GOOGLE ACCOUNT** (not your personal account!)
3. Click "Allow" to grant permissions
4. `token.json` is created automatically
5. Done! Future runs won't need browser login

⚠️ **CRITICAL:** Always use the community Google account, not your personal account!

### Step 5: Verify Installation

```bash
python -c "from gdrive_manager import GoogleDriveManager; print('✓ Module loaded successfully')"
```

If you see `✓ Module loaded successfully`, you're ready!

---

## 💻 Basic Usage

### Import the Module

```python
from gdrive_manager import GoogleDriveManager

# Initialize (handles authentication automatically)
drive = GoogleDriveManager()
```

### Upload a File

```python
# Upload to a specific folder
file_id = drive.upload_file(
    local_path="report.pdf",
    folder_id="your_folder_id_here"
)

print(f"Uploaded! File ID: {file_id}")
```

### Download a File

```python
# Download by file ID
success = drive.download_file(
    file_id="your_file_id_here",
    save_path="downloaded_report.pdf"
)

if success:
    print("Downloaded successfully!")
```

### List Files in a Folder

```python
# Get all files in a folder
files = drive.list_files(folder_id="your_folder_id_here")

for file_info in files:
    print(f"Name: {file_info['name']}, ID: {file_info['id']}")
```

### Create or Find a Folder

```python
# Get existing folder or create if it doesn't exist
folder_id = drive.get_or_create_folder(
    folder_name="Reports",
    parent_id=None  # None = root folder
)

print(f"Folder ID: {folder_id}")
```

---

## 🔧 Complete API Reference

### File Operations

```python
# Upload file
file_id = drive.upload_file(
    local_path="path/to/file.pdf",
    folder_id="folder_id_here",
    custom_name="renamed_file.pdf",  # Optional
    replace_existing=True,            # Optional: replace if exists
    mime_type="application/pdf"       # Optional: auto-detected
)

# Download file
success = drive.download_file(
    file_id="file_id_here",
    save_path="path/to/save.pdf"
)

# Delete file
success = drive.delete_file(file_id="file_id_here")
```

### Folder Operations

```python
# Create folder
folder_id = drive.create_folder(
    folder_name="New Folder",
    parent_id=None  # None = root, or provide parent folder ID
)

# Find or create folder (prevents duplicates)
folder_id = drive.get_or_create_folder(
    folder_name="Reports",
    parent_id=None
)
```

### Search Operations

```python
# Find a file by name
file_id = drive.find_file(
    file_name="report.pdf",
    folder_id="folder_id_here"  # Optional: search within folder
)

# Find a folder by name
folder_id = drive.find_folder(
    folder_name="Reports",
    parent_id=None  # Optional: search within parent
)

# List all files in a folder
files = drive.list_files(
    folder_id="folder_id_here",
    max_results=100,                    # Optional: default 100
    file_type="application/pdf"         # Optional: filter by MIME type
)
```

---

## 🎯 Real-World Examples

### Example 1: Generate and Upload Poster

```python
from gdrive_manager import GoogleDriveManager
from PIL import Image

# Initialize Drive
drive = GoogleDriveManager()

# Generate poster (example)
img = Image.new('RGB', (2000, 1414), color='white')
# ... add design elements ...
img.save("poster.jpg")

# Find output folder
folder_id = drive.get_or_create_folder("Generated Posters")

# Upload
file_id = drive.upload_file(
    local_path="poster.jpg",
    folder_id=folder_id,
    replace_existing=True
)

print(f"✓ Poster uploaded! File ID: {file_id}")
```

### Example 2: Download and Process Data

```python
from gdrive_manager import GoogleDriveManager
import pandas as pd

drive = GoogleDriveManager()

# Find the Excel file
file_id = drive.find_file("Meetup Planning Sheet.xlsx")

# Download it
drive.download_file(file_id, "local_data.xlsx")

# Process with pandas
df = pd.read_excel("local_data.xlsx")
print(f"Loaded {len(df)} rows")
```

### Example 3: Backup Files to Drive

```python
from gdrive_manager import GoogleDriveManager
import os

drive = GoogleDriveManager()

# Create backup folder
backup_folder = drive.create_folder("Backups 2025")

# Upload all PDFs in current directory
for filename in os.listdir("."):
    if filename.endswith(".pdf"):
        drive.upload_file(filename, backup_folder)
        print(f"✓ Backed up: {filename}")
```

---

## 🔒 Security & Best Practices

### ⚠️ Files to NEVER Commit to Git

The following files contain sensitive credentials and are automatically excluded by `.gitignore`:

- `credentials.json` — OAuth client credentials
- `token.json` — OAuth access token
- `event-agent-*.json` — Service account keys

**DO NOT:**
- ❌ Commit these files to Git
- ❌ Share via email or chat
- ❌ Upload to public repositories

**DO:**
- ✅ Use password manager for sharing (1Password, Bitwarden)
- ✅ Use encrypted storage
- ✅ Keep local copies secure

### Team Authentication Flow

1. **First team member:**
   - Creates `credentials.json` from Google Cloud Console
   - Runs first authentication → generates `token.json`
   - Shares `credentials.json` securely with team

2. **Other team members:**
   - Receive `credentials.json` from admin
   - Place in project folder
   - Run authentication → generates their own `token.json`

3. **Everyone uses the same:**
   - Community Google account for OAuth login
   - `credentials.json` (shared securely)

4. **Everyone has their own:**
   - `token.json` (generated locally, not shared)

---

## 🐛 Troubleshooting

### "OAuth authentication failed"

**Cause:** Wrong Google account used during login

**Fix:**
```bash
# Delete token and re-authenticate
rm token.json
python gdrive_manager.py
# Use COMMUNITY account this time!
```

---

### "Permission denied (403)"

**Cause:** File/folder not shared with your account

**Fix:**
- Ensure folder is shared with community Google account
- Check you have "Editor" permissions
- Ask admin to share the folder

---

### "File not found (404)"

**Cause:** Incorrect file/folder ID

**Fix:**
- Verify the file ID is correct
- Check if file was deleted
- Ensure you have access permissions

---

### "Quota exceeded (403)"

**Cause:** Drive storage is full

**Fix:**
- Free up space in Google Drive
- Delete old files
- Upgrade storage plan (if needed)

---

### "Module not found"

**Cause:** Dependencies not installed

**Fix:**
```bash
pip install -r requirements.txt
```

---

## 📁 Project Structure

```
Poster Agent/
├── gdrive_manager.py              ← Core module (commit this)
├── requirements.txt                ← Dependencies (commit this)
├── .gitignore                      ← Security exclusions (commit this)
├── GDRIVE_README.md                ← This file (commit this)
├── GDRIVE_USAGE_EXAMPLES.md        ← Code examples (commit this)
├── GDRIVE_INTEGRATION_SUMMARY.md   ← Technical details (commit this)
│
├── credentials.json                ← ⚠️ DO NOT COMMIT
├── token.json                      ← ⚠️ DO NOT COMMIT
└── event-agent-*.json              ← ⚠️ DO NOT COMMIT
```

---

## 📊 What to Include in PR

### Files to Commit:

✅ **Core Module:**
- `gdrive_manager.py`

✅ **Documentation:**
- `GDRIVE_README.md` (this file)
- `GDRIVE_USAGE_EXAMPLES.md`
- `GDRIVE_INTEGRATION_SUMMARY.md`

✅ **Configuration:**
- `requirements.txt`
- `.gitignore`

### Files to EXCLUDE:

❌ **Credentials (already in .gitignore):**
- `credentials.json`
- `token.json`
- `event-agent-*.json`

❌ **Generated/Cache:**
- `temp_downloads/`
- `posters_output/`
- `__pycache__/`
- `*.log`

---

## 🎓 How Other Agents Can Use This

### For Existing Agents:

1. Copy `gdrive_manager.py` to your agent's folder
2. Import and use: `from gdrive_manager import GoogleDriveManager`
3. First run: authenticate with community account
4. Done!

### For New Agents:

```python
from gdrive_manager import GoogleDriveManager

# Initialize
drive = GoogleDriveManager()

# Use any operation
file_id = drive.upload_file("output.pdf", folder_id)
```

**All agents share:**
- Same authentication system
- Same community account
- Same error handling
- Same API interface

---

## 📞 Support

### Common Questions:

**Q: Do I need to create my own Google Cloud project?**
A: No! Use the shared project. Just get `credentials.json` from admin.

**Q: Can I use my personal Google account?**
A: No! Always use the community Google account for consistency.

**Q: How do I get folder/file IDs?**
A: Use `find_folder()` or `find_file()` methods, or check Drive URL.

**Q: Is this safe for production?**
A: Yes! Includes comprehensive error handling and never crashes your agent.

---

## ✅ Quick Checklist

Before using the module:

- [ ] Python 3.7+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `credentials.json` placed in project folder
- [ ] `.gitignore` excludes sensitive files
- [ ] Authenticated with community Google account
- [ ] `token.json` generated successfully

---

## 🚀 Next Steps

1. **Get credentials** from project admin
2. **Install dependencies**: `pip install -r requirements.txt`
3. **First authentication**: `python gdrive_manager.py`
4. **Start building** your automation agent!

---

**The Google Drive Manager is ready to power all your automation agents!** 🎉

For detailed code examples, see `GDRIVE_USAGE_EXAMPLES.md`
For technical implementation details, see `GDRIVE_INTEGRATION_SUMMARY.md`
