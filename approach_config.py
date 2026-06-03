"""
Approach configuration — single source of truth for the approach hierarchy.
Loads from data/approaches.json; user can edit via the Options tab.
Handles bundled .app paths and provides migration for legacy approach names.
"""

import json
import re
import shutil
import sys
from pathlib import Path

# Legacy name → current name (for migrating old saves and learned rules)
LEGACY_NAMES: dict[str, str] = {
    "Lumostage":          "VPROD",
    "VP (INT. Vehicle)":  "INT. CAR",
    "VP (INT. Aircraft)": "INT. PLANE",
    "Set Build":          "HYBRID VIRTUAL",
    "On Location":        "LOCATION",
    "Option: Either":     "EITHER",
}

_DEFAULT_CONFIG: dict = {
    "version": 1,
    "solutions": ["CUSTOM/VAD", "UNREAL STOCK", "PRACTICAL PLATES", "VFX PLATES", "SET BUILD"],
    "approaches": [
        {"name": "VPROD",            "lumo": "YES", "colour": "FFF2CC", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": False, "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": False}},
        {"name": "INT. CAR",         "lumo": "YES", "colour": "E2EFDA", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": False, "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": False}},
        {"name": "INT. PLANE",       "lumo": "NO",  "colour": "D9EAD3", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": True }},
        {"name": "HYBRID VIRTUAL",   "lumo": "YES", "colour": "FCE4D6", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": False, "PRACTICAL PLATES": False, "VFX PLATES": False, "SET BUILD": False}},
        {"name": "INT. SUBWAY TRAIN","lumo": "YES", "colour": "C4D9F5", "solutions": {"CUSTOM/VAD": False, "UNREAL STOCK": False, "PRACTICAL PLATES": False, "VFX PLATES": True,  "SET BUILD": False}},
        {"name": "INT. PLATFORM",    "lumo": "YES", "colour": "B8D4F0", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": False, "VFX PLATES": True,  "SET BUILD": False}},
        {"name": "EXT. ROOFTOP",     "lumo": "YES", "colour": "D4EAD4", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": False}},
        {"name": "EXT. DESERT",      "lumo": "YES", "colour": "F5E6C4", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": True }},
        {"name": "EITHER",           "lumo": "NO",  "colour": "C8D8E0", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": True,  "VFX PLATES": True,  "SET BUILD": True }},
        {"name": "LOCATION",         "lumo": "NO",  "colour": "DDEBF7", "solutions": {"CUSTOM/VAD": False, "UNREAL STOCK": False, "PRACTICAL PLATES": False, "VFX PLATES": False, "SET BUILD": False}},
        {"name": "STUDIO",           "lumo": "NO",  "colour": "E8E8E8", "solutions": {"CUSTOM/VAD": False, "UNREAL STOCK": False, "PRACTICAL PLATES": False, "VFX PLATES": False, "SET BUILD": False}},
        {"name": "VFX",              "lumo": "NO",  "colour": "F4CCCC", "solutions": {"CUSTOM/VAD": True,  "UNREAL STOCK": True,  "PRACTICAL PLATES": False, "VFX PLATES": False, "SET BUILD": False}},
        {"name": "OMITTED",          "lumo": "NO",  "colour": "D9D9D9", "solutions": {"CUSTOM/VAD": False, "UNREAL STOCK": False, "PRACTICAL PLATES": False, "VFX PLATES": False, "SET BUILD": False}},
    ],
}


def _config_file() -> Path:
    if getattr(sys, 'frozen', False):
        user_data = Path.home() / "Library" / "Application Support" / "Slugger" / "data"
        user_data.mkdir(parents=True, exist_ok=True)
        f = user_data / "approaches.json"
        if not f.exists():
            bundled = Path(sys._MEIPASS) / "data" / "approaches.json"
            if bundled.exists():
                shutil.copy(bundled, f)
            else:
                _write(f, _DEFAULT_CONFIG)
        return f
    return Path(__file__).parent / "data" / "approaches.json"


def _write(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_config() -> dict:
    f = _config_file()
    if f.exists():
        try:
            with open(f, encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(_DEFAULT_CONFIG))


def save_config(config: dict) -> None:
    _write(_config_file(), config)


def get_approach_names(config: dict) -> list[str]:
    return [a["name"] for a in config.get("approaches", [])]


def get_lumo_names(config: dict) -> set[str]:
    return {a["name"] for a in config.get("approaches", []) if a.get("lumo") == "YES"}


def get_colours(config: dict) -> dict[str, str]:
    return {a["name"]: a.get("colour", "555555") for a in config.get("approaches", [])}


def get_solutions(config: dict) -> list[str]:
    return list(config.get("solutions", []))


def default_solutions_for(config: dict, approach_name: str) -> dict[str, bool]:
    sols = get_solutions(config)
    for a in config.get("approaches", []):
        if a["name"] == approach_name:
            return {s: bool(a.get("solutions", {}).get(s, False)) for s in sols}
    return {s: False for s in sols}


def get_approach_def(config: dict, name: str) -> dict | None:
    for a in config.get("approaches", []):
        if a["name"] == name:
            return a
    return None


def migrate_name(name: str) -> str:
    return LEGACY_NAMES.get(name, name)


def sol_key(sol: str) -> str:
    """Sanitise a solution name for use as a Streamlit session state key."""
    return re.sub(r"[^a-zA-Z0-9]", "_", sol)
