"""Colour console logger for the POC demo."""
import os, sys
from datetime import datetime

if sys.platform == "win32":
    os.system("")  # enable ANSI on Windows 10+

RST="\033[0m"; BLD="\033[1m"; DIM="\033[2m"
GRN="\033[92m"; YLW="\033[93m"; RED="\033[91m"
CYN="\033[96m"; PRP="\033[95m"; BLU="\033[94m"
WHT="\033[97m"; GRY="\033[90m"; ORG="\033[33m"

def _ts(): return datetime.now().strftime("%H:%M:%S")

def banner(title):
    line = "═"*62
    print(f"\n{PRP}{BLD}╔{line}╗\n║  {title:<60}║\n╚{line}╝{RST}")

def section(title, color=CYN):
    pad = max(0, 54 - len(title))
    print(f"\n{color}{BLD}┌─ {title} {'─'*pad}┐{RST}")

def end_section(color=CYN):
    print(f"{color}{BLD}└{'─'*58}┘{RST}")

def step(agent, msg):
    print(f"  {CYN}{BLD}[{_ts()}]{RST} {BLU}{BLD}{agent:<20}{RST} {msg}")

def ok(msg):   print(f"  {GRN}✓{RST}  {msg}")
def warn(msg): print(f"  {YLW}⚠{RST}  {msg}")
def fail(msg): print(f"  {RED}✗{RST}  {msg}")
def info(msg): print(f"  {GRY}ℹ{RST}  {DIM}{msg}{RST}")

def mock_call(api, action, result=""):
    r = f"  {GRN}↩ {result}{RST}" if result else ""
    print(f"  {YLW}[MOCK]{RST} {BLD}{api:<18}{RST} {action}{r}")

def write_back(field, value):
    short = str(value)[:65] + "…" if len(str(value)) > 65 else str(value)
    print(f"  {PRP}[SHEET WRITE]{RST} {BLD}{field}{RST} = {GRN}{short}{RST}")

def divider(): print(f"  {GRY}{'·'*58}{RST}")
def arrow(msg): print(f"  {CYN}▶{RST} {msg}")
