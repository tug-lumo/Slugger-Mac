"""
Save and load per-project breakdown state to/from disk.

Each project is saved as  saves/{safe_title}.json  containing:
  - scene-by-scene recommendations and notes
  - project-specific keyword rules
  - custom approach label additions
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path


def _saves_base() -> Path:
    if getattr(sys, 'frozen', False):
        d = Path.home() / "Library" / "Application Support" / "Slugger"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


SAVES_DIR = _saves_base() / "saves"


def _safe(title: str) -> str:
    return re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:80]


def save_path(title: str) -> Path:
    return SAVES_DIR / f"{_safe(title)}.json"


def _insert_scene_sorted(scenes: list, new_scene) -> None:
    """Insert new_scene at the correct position by numeric scene number."""
    def _num(s):
        m = re.match(r'^(\d+)', str(s.number or ''))
        return int(m.group(1)) if m else float('inf')
    new_n = _num(new_scene)
    for i, s in enumerate(scenes):
        if _num(s) > new_n:
            scenes.insert(i, new_scene)
            return
    scenes.append(new_scene)


def save_project(
    title: str,
    scenes: list,
    project_rules: list[dict] | None = None,
    custom_labels: list[str] | None = None,
) -> Path:
    SAVES_DIR.mkdir(exist_ok=True)
    data = {
        "title": title,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "scenes": {
            s.number: {
                "recommendation": s.recommendation,
                "vfx_notes": s.vfx_notes,
                "production_notes": s.production_notes,
            }
            for s in scenes
            if s.number and not getattr(s, "manually_added", False)
        },
        "manually_added_scenes": [
            {
                "number": s.number,
                "int_ext": s.int_ext,
                "location": s.location,
                "time_of_day": s.time_of_day,
                "raw_slug": s.raw_slug,
                "recommendation": s.recommendation,
                "vfx_notes": s.vfx_notes,
                "production_notes": s.production_notes,
            }
            for s in scenes
            if getattr(s, "manually_added", False)
        ],
        "project_rules": project_rules or [],
        "custom_labels": custom_labels or [],
    }
    path = save_path(title)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_project(title: str) -> dict | None:
    path = save_path(title)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_saves() -> list[Path]:
    SAVES_DIR.mkdir(exist_ok=True)
    return sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def apply_save_to_scenes(scenes: list, saved: dict) -> int:
    """
    Restore recommendations, notes, and manually-added scenes from a saved file.
    Returns the number of scenes updated/inserted.
    """
    from screenplay_parser import Scene

    # Re-insert manually-added scenes first so numbering is correct
    for s_data in saved.get("manually_added_scenes", []):
        new_scene = Scene(
            number=s_data["number"],
            int_ext=s_data["int_ext"],
            location=s_data["location"],
            time_of_day=s_data["time_of_day"],
            raw_slug=s_data["raw_slug"],
            page_start=0.0,
            recommendation=s_data.get("recommendation", ""),
            confidence="manual",
            vfx_notes=s_data.get("vfx_notes", ""),
            production_notes=s_data.get("production_notes", ""),
            manually_added=True,
        )
        _insert_scene_sorted(scenes, new_scene)

    scene_map: dict = saved.get("scenes", {})
    updated = 0
    for scene in scenes:
        if getattr(scene, "manually_added", False):
            continue
        entry = scene_map.get(scene.number)
        if entry:
            scene.recommendation   = entry.get("recommendation", scene.recommendation)
            scene.vfx_notes        = entry.get("vfx_notes", "")
            scene.production_notes = entry.get("production_notes", "")
            updated += 1
    return updated + len(saved.get("manually_added_scenes", []))


def apply_project_rules(scenes: list, rules: list[dict]) -> int:
    """
    Apply project-specific keyword rules to scenes in place.
    Each rule: {int_ext: "INT"|"EXT"|"BOTH", keyword: str, approach: str}
    Returns count of scenes changed.
    """
    changed = 0
    for scene in scenes:
        for rule in rules:
            ie_rule  = rule.get("int_ext", "BOTH").upper()
            keyword  = rule.get("keyword", "").upper().strip()
            approach = rule.get("approach", "").strip()
            if not keyword or not approach:
                continue
            # INT/EXT filter
            if ie_rule == "INT" and "INT" not in scene.int_ext.upper():
                continue
            if ie_rule == "EXT" and "EXT" not in scene.int_ext.upper():
                continue
            # Keyword match (word boundary)
            if re.search(r"\b" + re.escape(keyword) + r"\b", scene.location.upper()):
                if scene.recommendation != approach:
                    scene.recommendation = approach
                    changed += 1
                break  # first matching rule wins per scene
    return changed
