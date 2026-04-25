# Windows Installation Guide

## Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.10+ (3.11 recommended) | https://python.org/downloads |
| Git | Any | https://git-scm.com/download/win |
| Redis | 3.x | https://github.com/microsoftarchive/redis/releases |
| Chrome | Latest | https://www.google.com/chrome/ |

> Tip: during Python install, tick "Add Python to PATH".

## Step-by-Step Setup

### 1. Open a terminal

Use Command Prompt or PowerShell and switch to the repository root.

```cmd
cd C:\event-management-tool\Agentic-Event-Management
```

### 2. Remove a broken virtual environment if needed

```cmd
rmdir /s /q .venv
```

### 3. Run setup

```cmd
python setup.py
```

This will:
- Create `.venv`
- Install dependencies from `wimlds\requirements.txt`
- Create `wimlds\config\.env` from the example template when needed
- Check whether Redis and Chrome are available

### 4. If the pip step fails

```cmd
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r wimlds\requirements.txt
```

### 5. Activate the virtual environment

```cmd
.venv\Scripts\activate
```

### 6. Configure credentials

```cmd
notepad wimlds\config\.env
```

Fill in the placeholder values with your real credentials.

### 7. Start Redis

```cmd
redis-server
```

Or start the Windows service:

```cmd
net start Redis
```

### 8. Validate configuration

```cmd
python -m wimlds.scripts.validate_config
```

### 9. Run a dry run

```cmd
python run.py event --event-id 2 --dry-run
```

### 10. Go live

```cmd
python run.py event --event-id 2
```

## Common Windows Issues

### `'python' is not recognized`

Python is not on PATH. Reinstall Python and tick "Add Python to PATH", or run:

```cmd
py -3.11 setup.py
```

### `CalledProcessError` during pip upgrade

Use the manual install commands from Step 4.

### SSL certificate errors during pip install

```cmd
.venv\Scripts\python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r wimlds\requirements.txt
```

### `ModuleNotFoundError` when running `run.py`

Make sure the virtual environment is activated:

```cmd
.venv\Scripts\activate
```

### WhatsApp Web or browser automation cannot find Chrome

Install Chrome from https://www.google.com/chrome/.

### `redis.exceptions.ConnectionError`

Redis is not running. Start it with `redis-server` or the Windows service.

## Directory Layout on Windows

```text
C:\event-management-tool\
|-- Agentic-Event-Management\
|   |-- run.py
|   |-- setup.py
|   |-- .venv\
|   |-- docs\
|   '-- wimlds\
|       |-- requirements.txt
|       |-- config\
|       |   |-- .env
|       |   |-- .env.example
|       |   '-- service-account.json
|       |-- agents\
|       |-- core\
|       |-- integrations\
|       |-- scripts\
|       '-- tests\
```
