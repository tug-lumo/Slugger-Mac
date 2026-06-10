"""
Screenplay PDF parser with watermark filtering.

Primary strategy: number-anchored parse.
  Left-margin scene numbers are used as authoritative scene anchors.
  For each anchor, we search forward for the slug line, handling:
    - Normal slugs (INT./EXT. ... - TIME)
    - Broken/wrapped slugs split across two PDF lines
    - Non-standard headers (BLACK SCREEN, MONTAGE, etc.) with no INT./EXT.

Fallback strategy: slug-only parse (for scripts with no margin scene numbers).

Watermarks in these PDFs may use non-Courier fonts (Helvetica, Arial, Impact)
OR the same Courier font as the body, placed as floating text objects.
The font-name filter handles the former; for the latter, the margin-number
anchor strategy is resilient because watermark text never matches scene-number
or slug patterns at the correct x positions.
"""

import re
import fitz  # pymupdf
from dataclasses import dataclass, field
from typing import Optional

_SCREENPLAY_FONT_TOKENS = ("courier", "cour")

_SLUG_RE = re.compile(
    r"^(?:\d+[A-Z]?\s+)?"
    r"(INT\.|EXT\.|INT\./EXT\.|EXT\./INT\.|I/E\.)"
    r"\s+"
    r"(.+?)"
    r"\s*[-–—]\s*"
    r"(DAY|NIGHT|CONTINUOUS|LATER THAT (?:DAY|NIGHT|MORNING|EVENING)|LATER|MOMENTS LATER|"
    r"DAWN|DUSK|MORNING|EVENING|SUNSET|AFTERNOON|"
    r"ESTABLISHING|FLASHBACK|FLASH FORWARD|"
    r"UNDERWATER|DREAM|INTERCUT.*?|PRE-LAP|MAGIC HOUR|"
    r"SAME DAY|SAME NIGHT|SAME TIME|SAME MOMENT|SAME|"
    r"EARLIER THAT (?:DAY|NIGHT|MORNING|EVENING)|EARLIER|"
    r"PRESENT|PAST)"
    r"\.?"
    r"(?:\s*[\(\[].*?[\)\]])*"
    r"(?:\s+\d+[A-Z]?)?$",
    re.IGNORECASE,
)

# Fallback: broader match for non-standard time-of-day values.
_SLUG_FALLBACK_RE = re.compile(
    r"^(?:\d+[A-Z]?\s+)?"
    r"(INT\.|EXT\.|INT\./EXT\.|EXT\./INT\.|I/E\.)"
    r"\s+"
    r"(.+?)"
    r"\s*[-–—]\s*"
    r"([A-Z][A-Z0-9 ']{0,35})"
    r"\.?"
    r"(?:\s*[\(\[].*?[\)\]])*"
    r"(?:\s+\d+[A-Z]?)?$",
    re.IGNORECASE,
)

_SLUG_STARTS = ("INT.", "EXT.", "INT./EXT.", "EXT./INT.", "I/E.")


def _normalize_slug_prefix(text: str) -> str:
    """Collapse spacing variants: INT./ EXT. → INT./EXT., EXT./ INT. → EXT./INT."""
    text = re.sub(r"INT\.\s*/\s*EXT\.", "INT./EXT.", text, flags=re.IGNORECASE)
    text = re.sub(r"EXT\.\s*/\s*INT\.", "EXT./INT.", text, flags=re.IGNORECASE)
    return text

_SCENE_NUM_RE = re.compile(r"^\s*(\d+[A-Z]?)\s*$")

_TRANSITIONS = {
    "CUT TO:", "FADE IN:", "FADE IN", "FADE OUT:", "FADE OUT",
    "FADE TO:", "FADE TO BLACK.", "FADE TO BLACK",
    "MATCH CUT TO:", "SMASH CUT TO:", "JUMP CUT TO:",
    "DISSOLVE TO:", "WIPE TO:", "IRIS IN:", "IRIS OUT:",
    "TITLE CARD:", "SUPER:", "CHYRON:", "TITLE:", "INTERCUT WITH:",
    "THE END", "CONTINUED:", "CONT'D", "MORE",
    "END CREDITS", "BEGIN TITLES", "END TITLES",
    "CLOSE ON:", "CLOSE UP:", "INSERT:", "BACK TO SCENE",
    "SERIES OF SHOTS:", "SERIES OF SHOTS", "MONTAGE:", "END MONTAGE",
    "BEGIN MONTAGE", "LATER", "CONTINUOUS",
}


@dataclass
class Scene:
    number: Optional[str]
    int_ext: str
    location: str
    time_of_day: str
    raw_slug: str
    page_start: float
    page_end: float = 0.0
    page_count_str: str = ""
    description: str = ""
    characters: list = field(default_factory=list)
    recommendation: str = ""
    confidence: str = ""
    vfx_notes: str = ""
    production_notes: str = ""
    manually_added: bool = False
    volume_solutions: dict = field(default_factory=dict)
    stage_directions: str = ""
    stage_directions_notes: str = ""


def _is_screenplay_font(fontname: str) -> bool:
    name = fontname.lower()
    if "+" in name:
        name = name.split("+", 1)[1]
    name = name.replace("-", "").replace(" ", "").replace("_", "")
    return any(tok in name for tok in _SCREENPLAY_FONT_TOKENS)


def _eighths_str(page_count: float) -> str:
    total = round(page_count * 8)
    total = max(total, 1)
    whole, rem = divmod(total, 8)
    if whole > 0 and rem > 0:
        return f"{whole} {rem}/8"
    if whole > 0:
        return str(whole)
    return f"{rem}/8"


def _extract_lines(pdf_path: str) -> list[dict]:
    """
    Extract screenplay text lines from a PDF, filtering watermark spans by font.
    Returns list of dicts: {text, page, y, x, abs_pos, bold, page_height}
    """
    doc = fitz.open(pdf_path)
    all_lines: list[dict] = []

    for page_num, page in enumerate(doc, 1):
        page_height = page.rect.height
        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for block in page_dict["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                text_parts: list[str] = []
                is_bold = False
                has_screenplay = False

                for span in line["spans"]:
                    if _is_screenplay_font(span["font"]):
                        text_parts.append(span["text"])
                        has_screenplay = True
                        if "bold" in span["font"].lower():
                            is_bold = True

                if not has_screenplay:
                    continue

                text = "".join(text_parts).strip()
                if not text:
                    continue

                y0 = line["bbox"][1]
                x0 = line["bbox"][0]
                abs_pos = (page_num - 1) + (y0 / page_height)

                all_lines.append({
                    "text": text,
                    "page": page_num,
                    "y": y0,
                    "x": x0,
                    "abs_pos": abs_pos,
                    "bold": is_bold,
                    "page_height": page_height,
                })

    doc.close()
    # Sort by reading order: page + y position, then left-to-right within the
    # same y.  PyMuPDF block ordering is not guaranteed to be top-to-bottom,
    # and floating watermarks can appear in a different block order than the
    # body text on the same physical line.  Sorting ensures that the left-margin
    # scene number (x ≈ 60) always appears before the slug (x ≈ 89) when both
    # are on the same physical line.
    all_lines.sort(key=lambda l: (l["abs_pos"], l["x"]))
    return all_lines


# ── Slug-matching helpers ────────────────────────────────────────────────────

def _try_slug_match(text: str):
    """Try primary then fallback slug regex. Returns match or None."""
    text = _normalize_slug_prefix(text)
    m = _SLUG_RE.match(text)
    if m:
        return m
    stripped = re.sub(r"^\d+[A-Z]?\s+", "", text)
    if any(stripped.upper().startswith(s) for s in _SLUG_STARTS):
        return _SLUG_FALLBACK_RE.match(text)
    return None


def _slug_result(raw: str, m, pos: float):
    """
    Extract (raw_slug, int_ext, location, tod, abs_pos) from a regex match.
    Handles embedded leading scene numbers like "5 INT. PLACE - DAY 5".
    """
    embedded = re.match(r"^(\d+[A-Z]?)\s+", raw)
    if embedded:
        clean = re.sub(r"^\d+[A-Z]?\s+", "", raw)
        clean = re.sub(r"\s+\d+[A-Z]?$", "", clean).strip()
        m2 = _try_slug_match(clean)
        if m2:
            m = m2
    ie  = m.group(1).upper().rstrip(".")
    loc = m.group(2)
    tod = m.group(3)
    return (raw, ie, loc, tod, pos)


def _find_slug_in_range(lines: list, start: int, end: int):
    """
    Search lines[start:end] for a slug line.

    Handles broken slugs: when a line starts with INT./EXT. but doesn't
    complete the regex (e.g. "INT. VANCOUVER -"), we try joining it with
    subsequent lines (skipping standalone scene numbers) to form a complete
    slug.  This covers cases where a watermark or page layout splits a long
    slug across two text objects.

    Returns (raw_slug, int_ext, location, tod, abs_pos) or None.
    """
    i = start
    while i < end:
        text = lines[i]["text"]
        pos  = lines[i]["abs_pos"]

        if _SCENE_NUM_RE.match(text):
            i += 1
            continue

        m = _try_slug_match(text)
        if m:
            return _slug_result(text, m, pos)

        # Does it at least START with INT./EXT.?
        stripped = re.sub(r"^\d+[A-Z]?\s+", "", text)
        if any(_normalize_slug_prefix(stripped).upper().startswith(s) for s in _SLUG_STARTS):
            # Partial slug — accumulate subsequent all-caps continuation lines
            # until we form a complete slug.  Handles slugs split across two OR
            # three PDF text objects (e.g. "INT./EXT. CAR /" + "OTTAWA - BUILDING -"
            # + "DAY").  Watermarks ("Lumostage") are mixed-case and excluded by
            # the .isupper() guard.
            accumulated = text
            for j in range(i + 1, min(end, i + 10)):
                cont = lines[j]["text"]
                if _SCENE_NUM_RE.match(cont):
                    continue
                if not cont.isupper():
                    continue
                accumulated = accumulated + " " + cont
                m = _try_slug_match(accumulated)
                if m:
                    return _slug_result(accumulated, m, pos)
                # Stop if accumulated no longer resembles a slug prefix
                stripped_acc = re.sub(r"^\d+[A-Z]?\s+", "", accumulated)
                if not any(_normalize_slug_prefix(stripped_acc).upper().startswith(s) for s in _SLUG_STARTS):
                    break

        i += 1
    return None


def _synth_slug(lines: list, start: int, end: int, fallback_pos: float):
    """
    Synthesise a minimal slug for scenes that have no INT./EXT. header.
    Examples: BLACK SCREEN, CREDIT SEQUENCE BEGINS, TITLE CARD, MONTAGE.

    PyMuPDF block ordering is not guaranteed to be top-to-bottom, so watermarks
    at random y positions can appear before the actual scene header in the line
    list.  Strategy:
      1. Same physical line as the scene number (abs_pos within 0.02): these
         are aligned with the scene-number glyph and are almost certainly the
         real header, not a floating watermark.
      2. First all-caps line anywhere in the range: scene headers are always
         uppercase; mixed-case watermarks ("Lumostage") are excluded.
    """
    first_upper = None
    for i in range(start, end):
        text = lines[i]["text"].strip()
        if len(text) < 2 or _SCENE_NUM_RE.match(text):
            continue
        if abs(lines[i]["abs_pos"] - fallback_pos) <= 0.02:
            slug_text = text[:120]
            return (slug_text, "", slug_text.upper(), "", lines[i]["abs_pos"])
        if first_upper is None and text.isupper():
            first_upper = (text[:120], "", text[:120], "", lines[i]["abs_pos"])
    return first_upper or ("(NO HEADER)", "", "", "", fallback_pos)


def _fill_scene_content(scene: Scene, lines: list, start: int, end: int) -> None:
    """Extract character names, first description, and stage direction lines from a scene's text range."""
    action_lines: list[str] = []
    for i in range(start, end):
        line = lines[i]
        text = line["text"]
        if _SCENE_NUM_RE.match(text):
            continue
        if (
            text.isupper()
            and line["x"] > 140
            and len(text) < 55
            and not _SLUG_RE.match(text)
            and not text.strip().startswith("(")
            and not re.match(r"^[-=]+$", text)
        ):
            clean_name = re.sub(r"\s*\([^)]*\)\s*$", "", text.strip())
            if (
                clean_name not in _TRANSITIONS
                and clean_name not in scene.characters
                and len(clean_name) >= 2
            ):
                scene.characters.append(clean_name)
            continue
        if not scene.description and not text.isupper() and len(text) > 15:
            scene.description = text[:250]
        if (
            not text.isupper()
            and len(text.strip()) > 10
            and not text.strip().startswith("(")
            and line["x"] < 145
        ):
            action_lines.append(text.strip())
    scene.stage_directions = "\n".join(action_lines)


# ── Parse entry point ────────────────────────────────────────────────────────

def parse_screenplay(pdf_path: str) -> tuple[list[Scene], int]:
    """
    Parse a screenplay PDF.  Returns (scenes, total_page_count).

    Uses a two-strategy approach:
      1. Number-anchored (primary): if left-margin scene numbers are present,
         use them as authoritative anchors and find each scene's slug within
         its text range.  Handles broken slugs and non-standard headers.
      2. Slug-only (fallback): for scripts without margin numbers, detect
         scenes purely from INT./EXT. slug lines.
    """
    lines = _extract_lines(pdf_path)
    if not lines:
        return [], 0

    total_pages = int(lines[-1]["abs_pos"]) + 1

    # ── Collect left-margin scene-number anchors ─────────────────────────────
    # Left-margin numbers (x < 90pt) are the most reliable signal:
    # they appear on every numbered scene and are never confused with body text.
    anchors: list[tuple[str, int]] = []
    seen_nums: set[str] = set()
    for i, line in enumerate(lines):
        m = _SCENE_NUM_RE.match(line["text"])
        if m and line["x"] < 90:
            num = m.group(1)
            if num not in seen_nums:
                seen_nums.add(num)
                anchors.append((num, i))

    # ── Number-anchored parse ────────────────────────────────────────────────
    if anchors:
        scenes: list[Scene] = []

        for ai, (num, anchor_idx) in enumerate(anchors):
            next_anchor_idx = anchors[ai + 1][1] if ai + 1 < len(anchors) else len(lines)
            anchor_pos = lines[anchor_idx]["abs_pos"]

            result = _find_slug_in_range(lines, anchor_idx + 1, next_anchor_idx)
            if result:
                raw, ie, loc, tod, page_pos = result
            else:
                raw, ie, loc, tod, page_pos = _synth_slug(
                    lines,
                    anchor_idx + 1,
                    min(next_anchor_idx, anchor_idx + 10),
                    anchor_pos,
                )

            scene = Scene(
                number      = num,
                int_ext     = ie,
                location    = loc.upper().strip().replace("–", "-").replace("—", "-"),
                time_of_day = tod.upper().strip(),
                raw_slug    = raw,
                page_start  = page_pos,
            )
            scenes.append(scene)

        # Content extraction (characters, description)
        for si, scene in enumerate(scenes):
            next_idx = anchors[si + 1][1] if si + 1 < len(anchors) else len(lines)
            _fill_scene_content(scene, lines, anchors[si][1] + 1, next_idx)

        # Page counts
        for i, scene in enumerate(scenes):
            end = scenes[i + 1].page_start if i + 1 < len(scenes) else total_pages
            scene.page_end = end
            scene.page_count_str = _eighths_str(end - scene.page_start)

        return scenes, total_pages

    # ── Slug-only fallback (scripts without margin scene numbers) ────────────
    scenes = []
    pending_scene_num: Optional[str] = None

    for i, line in enumerate(lines):
        text = line["text"]

        # Standalone scene number
        nm = _SCENE_NUM_RE.match(text)
        if nm:
            if line["x"] < 90 or line["x"] > 430:
                candidate = nm.group(1)
                if not (scenes and scenes[-1].number == candidate):
                    pending_scene_num = candidate
            continue

        m = _try_slug_match(text)
        if m:
            embedded = re.match(r"^(\d+[A-Z]?)\s+", text)
            if embedded:
                scene_num = embedded.group(1)
                clean = re.sub(r"^\d+[A-Z]?\s+", "", text)
                clean = re.sub(r"\s+\d+[A-Z]?$", "", clean).strip()
                m2 = _try_slug_match(clean)
                if m2:
                    m = m2
                ie, loc, tod = m.group(1), m.group(2), m.group(3)
            else:
                scene_num = pending_scene_num
                ie, loc, tod = m.group(1), m.group(2), m.group(3)
            pending_scene_num = None

            scene = Scene(
                number      = scene_num or str(len(scenes) + 1),
                int_ext     = ie.upper().rstrip("."),
                location    = loc.upper().strip().replace("–", "-").replace("—", "-"),
                time_of_day = tod.upper().strip(),
                raw_slug    = text,
                page_start  = line["abs_pos"],
            )
            scenes.append(scene)
            continue

        if not scenes:
            continue
        current = scenes[-1]

        if (
            text.isupper()
            and line["x"] > 140
            and len(text) < 55
            and not _SLUG_RE.match(text)
            and not text.strip().startswith("(")
            and not re.match(r"^[-=]+$", text)
        ):
            clean_name = re.sub(r"\s*\([^)]*\)\s*$", "", text.strip())
            if (
                clean_name not in _TRANSITIONS
                and clean_name not in current.characters
                and len(clean_name) >= 2
            ):
                current.characters.append(clean_name)
            continue

        if not current.description and not text.isupper() and len(text) > 15:
            current.description = text[:250]
        if (
            not text.isupper()
            and len(text.strip()) > 10
            and not text.strip().startswith("(")
            and line["x"] < 145
        ):
            current.stage_directions = (
                current.stage_directions + "\n" + text.strip()
                if current.stage_directions else text.strip()
            )

    for i, scene in enumerate(scenes):
        end = scenes[i + 1].page_start if i + 1 < len(scenes) else total_pages
        scene.page_end = end
        scene.page_count_str = _eighths_str(end - scene.page_start)

    return scenes, total_pages
