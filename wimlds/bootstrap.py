"""Shared setup bootstrap for the WiMLDS automation project."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "wimlds"
VENV_DIR = PROJECT_ROOT / ".venv"
if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
REQUIREMENTS_FILE = PACKAGE_ROOT / "requirements.txt"
ENV_EXAMPLE = PACKAGE_ROOT / "config" / ".env.example"
ENV_FILE = PACKAGE_ROOT / "config" / ".env"


def _run(command: list[str]) -> None:
    print(f"> {' '.join(command)}")
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


def _ensure_venv() -> None:
    if VENV_PYTHON.exists():
        print(f"Using existing virtual environment: {VENV_DIR}")
        return
    print(f"Creating virtual environment: {VENV_DIR}")
    _run([sys.executable, "-m", "venv", str(VENV_DIR)])


def _install_requirements() -> None:
    print("Installing project dependencies...")
    _run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])


def _ensure_env_file() -> None:
    if ENV_FILE.exists():
        print(f"Environment file already present: {ENV_FILE}")
        return
    if not ENV_EXAMPLE.exists():
        print(f"Skipped .env creation because template is missing: {ENV_EXAMPLE}")
        return
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print(f"Created environment file from template: {ENV_FILE}")


def _check_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _check_chrome() -> bool:
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    return any(path.exists() for path in candidates)


def _print_checks() -> None:
    print("\nEnvironment checks:")
    print(f"- Redis available: {'yes' if _check_binary('redis-server') else 'no'}")
    print(f"- Chrome available: {'yes' if _check_chrome() else 'no'}")
    print(f"- Virtualenv Python: {VENV_PYTHON}")
    print(f"- Credentials file: {ENV_FILE}")


def main() -> None:
    print("WiMLDS project setup starting...")
    _ensure_venv()
    _install_requirements()
    _ensure_env_file()
    _print_checks()
    print("\nSetup complete.")
    print(f"Next: activate the venv and run `python run.py --help` from {PROJECT_ROOT}")


if __name__ == "__main__":
    main()
