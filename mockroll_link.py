"""
Slugger → Mock & Roll handoff: the "lumostage.script" file (version 1).

Mock & Roll (Lumostage's stage planner) imports this file to know the script: every scene's
number, slug, pages and eighths, characters, and the breakdown decided here (approach, whether it
plays on the volume, volume solutions, notes). Optionally it also carries the script text, split
into screenplay elements, so lines can be picked onto storyboard frames.

The same format is produced by Mock & Roll's in-browser PDF reader (for clients without Slugger),
so the two stay interchangeable. Format, all positions in PDF points from the top of the page:

{
  "format": "lumostage.script", "version": 1,
  "source": {"app": "Slugger", "exportedAt": ISO, "file": title},
  "title": str, "pages": int, "includesText": bool,
  "approaches": [{"name", "onVolume": bool, "colour": "#RRGGBB"}],
  "scenes": [{
     "n": "12", "slug": "INT. SUBWAY CAR - NIGHT", "ie": "INT", "loc": "SUBWAY CAR", "tod": "NIGHT",
     "page": 14, "pg": 13.42, "pgEnd": 14.1, "eighths": 5, "eighthsStr": "5/8",
     "chars": [...], "desc": str, "flags": [...],
     "approach": "VPROD", "onVolume": true, "solutions": ["CUSTOM/VAD", ...],
     "vfxNotes": str, "prodNotes": str, "stageNotes": str, "manual": false,
     "elements": [{"t": "slug|action|character|paren|dialogue|transition", "text": str,
                   "p": page, "y": top, "y2": bottom}]          # only when includesText
  }]
}

The scene list itself always comes from Slugger's parser (screenplay_parser.parse_screenplay);
this module only re-reads the page lines to split each scene's text into elements. It never
changes how Slugger finds scenes.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime

import fitz  # pymupdf

from screenplay_parser import _SCENE_NUM_RE, _is_screenplay_font, _try_slug_match, _is_nonstandard_scene_header

FORMAT = "lumostage.script"
VERSION = 1

_SKIP_RE = re.compile(r"^\(?(MORE|CONTINUED|CONT'D|CONT’D)\)?:?$|^CONTINUED[:\s(]", re.IGNORECASE)
_PAGE_NO_RE = re.compile(r"^\d+[A-Z]?\.?$")


def _lines_with_geometry(pdf_path: str) -> list[dict]:
    """Courier, horizontal, body-size lines only: drops watermarks in other fonts, rotated
    watermarks, and oversized floating text (watermarks set in the body font)."""
    doc = fitz.open(pdf_path)
    out: list[dict] = []
    for page_num, page in enumerate(doc, 1):
        ph = page.rect.height
        for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                dx, dy = line.get("dir", (1, 0))
                if abs(dy) > 0.01 or dx < 0:
                    continue                                   # rotated / diagonal text = watermark
                spans = [s for s in line["spans"] if _is_screenplay_font(s["font"]) and 8.5 <= s["size"] <= 14.5]
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                x0 = min(s["bbox"][0] for s in spans)
                y0 = min(s["bbox"][1] for s in spans)
                y1 = max(s["bbox"][3] for s in spans)
                out.append({"text": text, "page": page_num, "x": x0, "y": y0, "y2": y1,
                            "abs_pos": (page_num - 1) + y0 / ph, "ph": ph})
    doc.close()
    out.sort(key=lambda l: (l["abs_pos"], l["x"]))
    return _drop_tiled_watermarks(out)


def _drop_tiled_watermarks(lines: list[dict]) -> list[dict]:
    """Watermarks set in the body font at body size ("Lumostage", a recipient's name) survive the
    font/size/rotation filters. They give themselves away by repeating on many pages and by not
    sitting on the script's 12 pt line grid (Courier 12 is 6 lines per inch)."""
    if not lines:
        return lines
    pages = max(l["page"] for l in lines)
    grid = {}
    for pg in set(l["page"] for l in lines):
        c = Counter(round(l["y"] % 12) % 12 for l in lines if l["page"] == pg)
        grid[pg] = c.most_common(1)[0][0]
    def off_grid(l):
        d = abs((l["y"] - grid[l["page"]]) % 12)
        return min(d, 12 - d) > 1.5
    by_text: dict[str, list[dict]] = {}
    for l in lines:
        by_text.setdefault(l["text"].strip(), []).append(l)
    marks = set()
    for t, ls in by_text.items():
        pgs = set(l["page"] for l in ls)
        if len(pgs) < max(3, 0.25 * pages):
            continue
        off = sum(1 for l in ls if off_grid(l)) / len(ls)
        per_page = len(ls) / len(pgs)
        mixed = any(ch.islower() for ch in t)
        if (mixed and (per_page >= 2 or off >= 0.5)) or off >= 0.6:
            marks.add(t)
    kept = [l for l in lines if l["text"].strip() not in marks]
    # A watermark word can also be fused into a real line by the PDF ("BAINSLumostage",
    # "Lumostage SUNSET"): strip mixed-case marks out of the text that's left.
    inner = [m for m in marks if len(m) >= 4 and any(ch.islower() for ch in m)]
    if inner:
        pat = re.compile("|".join(re.escape(m) for m in sorted(inner, key=len, reverse=True)))
        for l in kept:
            if pat.search(l["text"]):
                l["text"] = re.sub(r"\s{2,}", " ", pat.sub(" ", l["text"])).strip()
        kept = [l for l in kept if l["text"]]
    return kept


def _action_indent(lines: list[dict]) -> float:
    """The page's action / slug indent (normally 1.5 in = 108 pt), from the most common left edge."""
    xs = Counter(round(l["x"] / 2) * 2 for l in lines if 90 <= l["x"] < 145)
    return float(xs.most_common(1)[0][0]) if xs else 108.0


def classify(line: dict, base: float) -> str | None:
    """Screenplay element type from indent and case; None for furniture (scene/page numbers, MORE)."""
    s = line["text"].strip()
    dx = line["x"] - base
    if line["y"] < 60 or line["y"] > line["ph"] - 48:
        return None                                            # running header / footer band
    if re.fullmatch(r"[*\s]+", s):
        return None                                            # revision asterisks in the margin
    if _SCENE_NUM_RE.match(s) and (line["x"] < 90 or line["x"] > 430):
        return None
    if _PAGE_NO_RE.match(s) and (line["y"] < 72 or line["y"] > line["ph"] - 60):
        return None
    if _SKIP_RE.match(s):
        return None
    if dx < 25 and (_try_slug_match(s) or _is_nonstandard_scene_header(s, line["x"])):
        return "slug"
    letters = re.sub(r"[^A-Za-z]", "", s)
    if dx >= 230 or (letters and s.isupper() and s.endswith(":") and dx > 150):
        return "transition"
    if s.startswith("(") and 40 <= dx < 150:
        return "paren"
    if letters and s.upper() == s and dx >= 110 and len(s) < 55:
        return "character"
    if 40 <= dx < 110:
        return "dialogue"
    return "action"


def _merge(elements: list[dict]) -> list[dict]:
    """Join wrapped lines of one paragraph (same type, same page, next line down)."""
    out: list[dict] = []
    for e in elements:
        prev = out[-1] if out else None
        if (prev and e["t"] == prev["t"] and e["t"] in ("action", "dialogue", "paren")
                and e["p"] == prev["p"] and 0 <= e["y"] - prev["y2"] < 6):
            prev["text"] += " " + e["text"]
            prev["y2"] = e["y2"]
        else:
            out.append(dict(e))
    return out


def scene_elements(pdf_path: str, scenes: list) -> dict[str, list[dict]]:
    """Map scene number → its screenplay elements, using the scene starts Slugger already found."""
    lines = _lines_with_geometry(pdf_path)
    if not lines:
        return {}
    base = _action_indent(lines)
    starts = [(s.page_start, s.number) for s in scenes if s.number and not getattr(s, "manually_added", False) and s.page_start]
    starts.sort()
    result: dict[str, list[dict]] = {}
    for k, (start, num) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else float("inf")
        els = []
        for l in lines:
            if l["abs_pos"] < start - 1e-6 or l["abs_pos"] >= end - 1e-6:
                continue
            t = classify(l, base)
            if t:
                els.append({"t": t, "text": l["text"].strip(), "p": l["page"], "y": round(l["y"], 1), "y2": round(l["y2"], 1)})
        result[num] = _merge(els)
    return result


def _clean_slug(raw: str) -> str:
    s = re.sub(r"^\d+[A-Z]?\s+", "", (raw or "").strip())
    return re.sub(r"\s+\d+[A-Z]?$", "", s).strip()


def build_handoff(scenes: list, title: str, total_pages: int, config: dict | None = None,
                  include_text: bool = False, pdf_bytes: bytes | None = None) -> dict:
    """The lumostage.script dict for these scenes. Pass pdf_bytes with include_text=True."""
    approaches, on_vol = [], {}
    if config:
        for a in config.get("approaches", []):
            on = str(a.get("lumo", "NO")).upper() == "YES"
            on_vol[a["name"]] = on
            approaches.append({"name": a["name"], "onVolume": on, "colour": "#" + str(a.get("colour", "D9D9D9")).lstrip("#")})
    elements: dict[str, list[dict]] = {}
    if include_text and pdf_bytes:
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(pdf_bytes)
            elements = scene_elements(tmp, scenes)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    out_scenes = []
    for s in scenes:
        rec = getattr(s, "recommendation", "") or ""
        sols = getattr(s, "volume_solutions", {}) or {}
        start, end = float(s.page_start or 0), float(getattr(s, "page_end", 0) or 0)
        sc = {
            "n": str(s.number or ""), "slug": _clean_slug(s.raw_slug), "ie": s.int_ext or "", "loc": s.location or "",
            "tod": s.time_of_day or "", "page": int(start) + 1 if start or not getattr(s, "manually_added", False) else None,
            "pg": round(start, 3), "pgEnd": round(end, 3), "eighths": max(1, round((end - start) * 8)) if end > start else None,
            "eighthsStr": getattr(s, "page_count_str", "") or "", "chars": list(getattr(s, "characters", []) or []),
            "desc": getattr(s, "description", "") or "", "flags": list(getattr(s, "flags", []) or []),
            "approach": rec, "onVolume": on_vol.get(rec), "solutions": [k for k, v in sols.items() if v],
            "vfxNotes": getattr(s, "vfx_notes", "") or "", "prodNotes": getattr(s, "production_notes", "") or "",
            "stageNotes": getattr(s, "stage_directions_notes", "") or "", "manual": bool(getattr(s, "manually_added", False)),
        }
        if include_text:
            sc["elements"] = elements.get(str(s.number), [])
        out_scenes.append(sc)
    return {
        "format": FORMAT, "version": VERSION,
        "source": {"app": "Slugger", "exportedAt": datetime.now().isoformat(timespec="seconds"), "file": title},
        "title": title, "pages": int(total_pages or 0), "includesText": bool(include_text and elements),
        "approaches": approaches, "scenes": out_scenes,
    }


def handoff_bytes(*args, **kwargs) -> bytes:
    return json.dumps(build_handoff(*args, **kwargs), ensure_ascii=False, indent=1).encode("utf-8")
