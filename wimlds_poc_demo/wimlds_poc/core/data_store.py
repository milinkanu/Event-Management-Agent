"""Local JSON data store — replaces Google Sheets + Redis for the POC demo."""
import json, copy
from pathlib import Path
from datetime import datetime

_ROOT      = Path(__file__).parent.parent
DATA_FILE  = _ROOT / "config" / "event_data.json"
STATE_FILE = _ROOT / "output"  / "event_state.json"
STATE_FILE.parent.mkdir(exist_ok=True)

def load_event(row_number: int) -> dict:
    data = json.loads(DATA_FILE.read_text())
    for ev in data["events"]:
        if ev["_row_number"] == row_number:
            state  = _load_state().get(str(row_number), {})
            merged = copy.deepcopy(ev)
            merged.update(state)
            return merged
    raise ValueError(f"No event with row_number={row_number}")

def write_fields(row_number: int, fields: dict):
    state = _load_state()
    key   = str(row_number)
    state.setdefault(key, {}).update(fields)
    state[key]["_last_updated"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))

def write_field(row_number: int, field: str, value):
    write_fields(row_number, {field: value})

def set_flag(row_number: int, flag: str, value: str = "Y"):
    write_field(row_number, flag, value)

def reset_event(row_number: int):
    state = _load_state()
    state.pop(str(row_number), None)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_written_back(row_number: int) -> dict:
    return _load_state().get(str(row_number), {})

def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
