"""
Screenplay Breakdown Tool — Streamlit UI
Runs 100% locally. No data leaves your machine.
"""

import base64
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import fitz  # pymupdf — for page rendering
import pandas as pd
import streamlit as st

from approach_config import (
    load_config, save_config,
    get_approach_names, get_lumo_names, get_colours,
    get_solutions, default_solutions_for, get_approach_def,
    sol_key as _sk, LEGACY_NAMES,
)
from screenplay_parser import parse_screenplay, Scene
from vp_heuristics import (
    R_VPROD, R_INT_CAR, R_INT_PLANE, R_HYBRID_VIRTUAL,
    R_SUBWAY_TRAIN, R_PLATFORM, R_ROOFTOP, R_DESERT,
    R_EITHER, R_LOCATION, R_STUDIO, R_VFX, R_OMITTED,
    load_rules,
    learn_from_edits,
    recommend_vp,
    rule_stats,
)
from exporter import (
    export_to_excel, import_from_excel, apply_excel_import,
    _eighths_to_float, _eighths_str_from_float,
)
from project_state import (
    save_project,
    load_project,
    list_saves,
    apply_save_to_scenes,
    apply_project_rules,
    _insert_scene_sorted,
)

# ── Logo assets ───────────────────────────────────────────────────────────────

def _b64_img(path: Path) -> str:
    if path.exists():
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    return ""

_LOGO_DIR    = Path(__file__).parent
_EMBLEM_URI  = _b64_img(_LOGO_DIR / "Lumostage_Emblem_RGB.png")
_PRIMARY_URI = _b64_img(_LOGO_DIR / "Lumostage_Primary_FullColour_RGB--whitetext.png")


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Slugger — VP Breakdown",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    :root {
        --lumo-seafoam:  #00EFEA;
        --lumo-blue:     #0060FE;
        --lumo-deepblue: #144BA0;
        --lumo-salmon:   #FF6169;
        --lumo-dark:     #13191A;
        --lumo-panel:    #1C2427;
        --lumo-light:    #F2F2F2;
    }
    .slugger-word {
        font-size: 2.0rem; font-weight: 900; letter-spacing: 0.12em;
        line-height: 1; color: #F2F2F2; text-transform: uppercase;
        text-shadow: 3px 3px 0px #0060FE, 0 0 18px #00EFEA55;
        font-style: italic;
    }
    .slugger-word .glove { font-style: normal; margin-right: 4px; }
    .slugger-word-sm {
        font-size: 1.35rem; font-weight: 900; letter-spacing: 0.1em;
        color: #F2F2F2;
        text-shadow: 2px 2px 0px #0060FE, 0 0 12px #00EFEA44;
        font-style: italic;
    }
    .slugger-tagline {
        font-size: 0.65rem; color: #8ABAC8; letter-spacing: 0.07em;
        font-style: italic; margin-top: 1px;
    }
    #MainMenu { visibility: hidden; }
    header[data-testid="stHeader"] { display: none; }
    [data-testid="stToolbar"] { display: none; }
    .block-container { padding-top: 0.75rem; }
    [data-testid="stSidebar"] {
        border-right: 1px solid #00EFEA22; background: #0E1416;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 0.82rem; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px; border-bottom: 2px solid #0060FE35; padding: 0 4px;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600; font-size: 0.88rem; letter-spacing: 0.05em;
        padding: 12px 28px; color: #8ABAC8;
        border-radius: 4px 4px 0 0; transition: color 0.15s, background 0.15s;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #C8DDE8 !important; background: #1C242720 !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #00EFEA !important; border-bottom: 3px solid #00EFEA !important;
        background: #00EFEA0A !important;
    }
    .script-banner {
        background: linear-gradient(135deg, #13191A 0%, #1C2427 100%);
        border: 1px solid #0060FE30; border-radius: 10px;
        padding: 16px 24px 12px 24px; margin-bottom: 12px;
    }
    .banner-title { font-size: 1.25rem; font-weight: 800; color: #F2F2F2; letter-spacing: 0.04em; line-height: 1.2; margin-bottom: 2px; }
    .banner-sub { font-size: 0.75rem; color: #8ABAC8; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }
    .banner-pills { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
    .b-pill {
        background: #0D1F35; border: 1px solid #0060FE40; border-radius: 20px;
        padding: 4px 14px; display: flex; align-items: baseline; gap: 6px;
    }
    .b-pill-num { font-size: 1.05rem; font-weight: 700; color: #F2F2F2; font-variant-numeric: tabular-nums; }
    .b-pill-label { font-size: 0.68rem; color: #8ABAC8; text-transform: uppercase; letter-spacing: 0.08em; }
    .b-pill-num.accent { color: #00EFEA; }
    .approach-bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; gap: 1px; margin-top: 4px; }
    .approach-bar-legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; }
    .abl-item { display: flex; align-items: center; gap: 5px; font-size: 0.72rem; color: #8ABAC8; }
    .abl-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
    .stDataFrame thead tr th { background-color: #144BA0 !important; color: white !important; }
    .scene-slug {
        font-family: 'Courier New', monospace; font-size: 0.85rem;
        background: #1C2427; padding: 8px 12px; border-radius: 4px;
        border-left: 3px solid #00EFEA; color: #F2F2F2; margin-bottom: 4px;
    }
    .scene-meta { font-size: 0.8rem; color: #8ABAC8; margin-top: 4px; }
    .approach-summary {
        background: #1C2427; border: 1px solid #0060FE35;
        border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;
    }
    .approach-summary h4 { color: #00EFEA; margin: 0 0 12px 0; font-size: 0.9rem; letter-spacing: 0.08em; text-transform: uppercase; }
    .as-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #0060FE18; font-size: 0.84rem; }
    .as-row:last-child { border-bottom: none; }
    .as-label { color: #C8D8E0; flex: 3; }
    .as-label.lumo  { color: #FFE08A; }
    .as-label.loc   { color: #8ABAC8; }
    .as-label.vfx   { color: #FF8A8A; }
    .as-label.either { color: #D0D8E0; }
    .as-label.total { color: #F2F2F2; font-weight: 700; font-size: 0.88rem; }
    .as-num { flex: 1; text-align: right; color: #C8D8E0; font-variant-numeric: tabular-nums; }
    .as-num.total { font-weight: 700; color: #00EFEA; font-size: 0.88rem; }
    .as-divider { border: none; border-top: 1px solid #0060FE40; margin: 6px 0; }
    .as-col-headers { display: flex; justify-content: space-between; padding: 0 0 6px 0; font-size: 0.7rem; color: #0060FE; text-transform: uppercase; letter-spacing: 0.1em; border-bottom: 1px solid #0060FE25; margin-bottom: 4px; }
    .as-col-headers span:first-child { flex: 3; }
    .as-col-headers span { flex: 1; text-align: right; }
    .sb-section-title { font-size: 0.65rem; color: #0060FE; text-transform: uppercase; letter-spacing: 0.12em; margin: 14px 0 6px 0; border-bottom: 1px solid #0060FE25; padding-bottom: 4px; }
    .sb-approach-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
    .sb-approach-label { font-size: 0.74rem; color: #C8D8E0; flex: 0 0 auto; width: 106px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sb-bar-track { flex: 1; height: 5px; background: #1C2427; border-radius: 3px; overflow: hidden; }
    .sb-bar-fill { height: 5px; border-radius: 3px; }
    .sb-approach-pct { font-size: 0.7rem; color: #8ABAC8; font-variant-numeric: tabular-nums; flex: 0 0 28px; text-align: right; }
    .sb-ie-pills { display: flex; gap: 8px; margin-top: 4px; }
    .sb-ie-pill { flex: 1; background: #1C2427; border: 1px solid #0060FE30; border-radius: 6px; padding: 6px 8px; text-align: center; }
    .sb-ie-label { font-size: 0.62rem; color: #0060FE; text-transform: uppercase; letter-spacing: 0.1em; display: block; }
    .sb-ie-num { font-size: 1.0rem; font-weight: 700; color: #F2F2F2; display: block; }
    .sb-ie-pct { font-size: 0.65rem; color: #8ABAC8; display: block; }
    .sb-loc-row { display: flex; justify-content: space-between; font-size: 0.74rem; color: #C8D8E0; padding: 3px 0; border-bottom: 1px solid #0060FE12; }
    .sb-loc-row:last-child { border-bottom: none; }
    .sb-loc-name { color: #C8D8E0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px; }
    .sb-loc-pages { color: #8ABAC8; font-variant-numeric: tabular-nums; flex-shrink: 0; margin-left: 6px; }
    .vol-sol-label { font-size: 0.68rem; color: #8ABAC8; text-transform: uppercase; letter-spacing: 0.08em; margin: 10px 0 2px 0; }
    [data-testid="stMetricLabel"] { color: #8ABAC8 !important; }
    [data-testid="stMetricValue"] { color: #F2F2F2 !important; }
</style>
""", unsafe_allow_html=True)


# ── Cached PDF page renderer ──────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def render_page(pdf_bytes: bytes, page_idx: int, zoom: float = 1.5) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_idx]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    png = pix.tobytes("png")
    doc.close()
    return png


# ── Session state init ────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "rules":            load_rules(),
        "approach_config":  load_config(),
        "scenes":           [],
        "df":               None,
        "pdf_bytes":        None,
        "script_title":     "",
        "total_pages":      0,
        "last_uploaded":    "",
        "reader_scene_idx": 0,
        "reader_page_idx":  0,
        "project_rules":    [],
        "custom_labels":    [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# Convenience accessors
_ac = st.session_state["approach_config"]
_APPROACH_COLOURS: dict[str, str] = get_colours(_ac)
_APPROACH_DISPLAY_ORDER: list[str] = get_approach_names(_ac)
_LUMO_NAMES: set[str] = get_lumo_names(_ac)
_SOLUTIONS: list[str] = get_solutions(_ac)
_SOL_ABBREV = {
    "CUSTOM/VAD":      "VAD",
    "UNREAL STOCK":    "UNREAL",
    "PRACTICAL PLATES":"PRACT.",
    "VFX PLATES":      "VFX PLT",
    "SET BUILD":       "SET BLD",
}


def _options() -> list[str]:
    base = get_approach_names(st.session_state["approach_config"])
    custom = st.session_state.get("custom_labels", [])
    return base + [l for l in custom if l not in base]


def _scene_gaps(scenes: list) -> list[int]:
    nums = sorted({
        int(m.group(1))
        for s in scenes
        if s.number and (m := re.match(r'^(\d+)', str(s.number)))
        and not getattr(s, 'manually_added', False)
    })
    if len(nums) < 2:
        return []
    gaps: list[int] = []
    for i in range(len(nums) - 1):
        if nums[i + 1] - nums[i] > 1:
            gaps.extend(range(nums[i] + 1, nums[i + 1]))
    return gaps


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    _emblem_tag = (
        f"<img src='{_EMBLEM_URI}' style='"
        f"width:38px;height:38px;object-fit:contain;"
        f"background:#fff;border-radius:8px;padding:4px;flex-shrink:0'>"
    ) if _EMBLEM_URI else ""

    st.markdown(
        f"<div style='padding:12px 0 0 0'>"
        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:4px'>"
        f"{_emblem_tag}"
        f"<div>"
        f"<div class='slugger-word-sm'><span class='glove'>🥊</span>SLUGGER</div>"
        f"<div class='slugger-tagline'>Taking the mental out of breakdowns</div>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    st.divider()

    uploaded = st.file_uploader(
        "Upload a screenplay PDF", type=["pdf"],
        help="Watermarks filtered automatically by font.",
    )

    _sb_scenes = st.session_state.get("scenes", [])
    _sb_title  = st.session_state.get("script_title", "")

    if _sb_scenes and _sb_title:
        _sb_total_pages = sum(_eighths_to_float(s.page_count_str) for s in _sb_scenes)

        _sb_summary: dict[str, dict] = defaultdict(lambda: {"scenes": 0, "pages": 0.0})
        for _s in _sb_scenes:
            _k = _s.recommendation if isinstance(_s.recommendation, str) and _s.recommendation else "Unassigned"
            _sb_summary[_k]["scenes"] += 1
            _sb_summary[_k]["pages"]  += _eighths_to_float(_s.page_count_str)

        _lumo_pages_sb = sum(v["pages"] for k, v in _sb_summary.items() if k in _LUMO_NAMES)
        _lumo_pct_sb   = int(_lumo_pages_sb / _sb_total_pages * 100) if _sb_total_pages else 0

        _bar_segs = ""
        _legend_items = ""
        _sb_order = _APPROACH_DISPLAY_ORDER + sorted(k for k in _sb_summary if k not in _APPROACH_DISPLAY_ORDER)
        for _a in _sb_order:
            if _a not in _sb_summary:
                continue
            _pgs = _sb_summary[_a]["pages"]
            _pct = (_pgs / _sb_total_pages * 100) if _sb_total_pages else 0
            if _pct < 1:
                continue
            _col = _APPROACH_COLOURS.get(_a, "555555")
            _bar_segs += f"<div style='flex:{_pct:.1f};background:#{_col}'></div>"
            _legend_items += (
                f"<div class='abl-item'>"
                f"<div class='abl-dot' style='background:#{_col}'></div>"
                f"<span>{_a}&nbsp;{_pct:.0f}%</span>"
                f"</div>"
            )

        _approach_rows_html = ""
        for _a in _sb_order:
            if _a not in _sb_summary:
                continue
            _d = _sb_summary[_a]
            _pct = (_d["pages"] / _sb_total_pages * 100) if _sb_total_pages else 0
            if _pct < 0.5:
                continue
            _col = _APPROACH_COLOURS.get(_a, "555555")
            _approach_rows_html += (
                f"<div class='sb-approach-row'>"
                f"<div class='sb-approach-label' title='{_a}'>{_a}</div>"
                f"<div class='sb-bar-track'>"
                f"<div class='sb-bar-fill' style='width:{_pct:.1f}%;background:#{_col}'></div>"
                f"</div>"
                f"<div class='sb-approach-pct'>{_pct:.0f}%</div>"
                f"</div>"
            )

        _int_n  = sum(1 for _s in _sb_scenes if _s.int_ext == "INT")
        _ext_n  = sum(1 for _s in _sb_scenes if _s.int_ext == "EXT")
        _ie_n   = sum(1 for _s in _sb_scenes if _s.int_ext in ("INT/EXT", "EXT/INT"))
        _oth_n  = len(_sb_scenes) - _int_n - _ext_n - _ie_n
        _total_n = len(_sb_scenes)
        _int_pct = _int_n / _total_n * 100 if _total_n else 0
        _ext_pct = _ext_n / _total_n * 100 if _total_n else 0
        _ie_pct  = _ie_n  / _total_n * 100 if _total_n else 0

        ie_html = (
            "<div class='sb-ie-pills'>"
            f"<div class='sb-ie-pill'><span class='sb-ie-label'>INT</span>"
            f"<span class='sb-ie-num'>{_int_n}</span><span class='sb-ie-pct'>{_int_pct:.0f}%</span></div>"
            f"<div class='sb-ie-pill'><span class='sb-ie-label'>EXT</span>"
            f"<span class='sb-ie-num'>{_ext_n}</span><span class='sb-ie-pct'>{_ext_pct:.0f}%</span></div>"
            f"<div class='sb-ie-pill'><span class='sb-ie-label'>INT/EXT</span>"
            f"<span class='sb-ie-num'>{_ie_n + _oth_n}</span><span class='sb-ie-pct'>{_ie_pct:.0f}%</span></div>"
            "</div>"
        )

        _loc_pages: dict[str, float] = defaultdict(float)
        for _s in _sb_scenes:
            _root = _s.location.split(" - ")[0].strip() if _s.location else "(none)"
            _loc_pages[_root] += _eighths_to_float(_s.page_count_str)
        _top_locs = sorted(_loc_pages.items(), key=lambda x: -x[1])[:6]
        _loc_rows_html = "".join(
            f"<div class='sb-loc-row'>"
            f"<span class='sb-loc-name' title='{_ln}'>{_ln}</span>"
            f"<span class='sb-loc-pages'>{_eighths_str_from_float(_lp)} pg</span>"
            f"</div>"
            for _ln, _lp in _top_locs
        )

        st.markdown(
            f"<div class='sb-section-title'>{_sb_title[:28]}</div>"
            f"<div style='font-size:0.74rem;color:#8ABAC8;margin-bottom:8px'>"
            f"{len(_sb_scenes)} scenes &nbsp;·&nbsp; {_sb_total_pages:.1f} pages &nbsp;·&nbsp; "
            f"<span style='color:#00EFEA;font-weight:600'>{_lumo_pct_sb:.0f}% Lumostage</span></div>"
            f"<div class='approach-bar' style='margin-bottom:4px'>{_bar_segs}</div>"
            f"<div class='approach-bar-legend' style='margin-bottom:12px'>{_legend_items}</div>"
            f"<div class='sb-section-title'>Approach breakdown</div>"
            f"{_approach_rows_html}"
            f"<div class='sb-section-title'>INT / EXT</div>"
            f"{ie_html}"
            f"<div class='sb-section-title'>Top locations</div>"
            f"{_loc_rows_html}",
            unsafe_allow_html=True,
        )

    st.divider()

    stats = rule_stats(st.session_state.rules)
    _rules_total = stats["total"]
    st.markdown(
        f"<div class='sb-section-title'>Learned rules &nbsp;"
        f"<span style='color:#F2F2F2;font-weight:700'>{_rules_total}</span></div>",
        unsafe_allow_html=True,
    )
    if stats["by_recommendation"]:
        _rules_lines = "".join(
            f"<div style='font-size:0.72rem;color:#8ABAC8;padding:2px 0'>"
            f"<span style='color:#C8D8E0'>{_rc}</span> &nbsp;{_rn}</div>"
            for _rc, _rn in sorted(stats["by_recommendation"].items(), key=lambda x: -x[1])
        )
        st.markdown(_rules_lines, unsafe_allow_html=True)

    if st.button("Clear learned rules", use_container_width=True):
        st.session_state.rules = {"learned": {}, "version": 1}
        from vp_heuristics import save_rules
        save_rules(st.session_state.rules)
        st.success("Rules cleared.")


# ── Parse on new upload ───────────────────────────────────────────────────────

if uploaded and st.session_state.last_uploaded != uploaded.name:
    st.session_state.last_uploaded = uploaded.name
    title_stem = Path(uploaded.name).stem
    st.session_state.script_title = title_stem
    st.session_state.pdf_bytes = uploaded.getvalue()

    for k in ("scene_jump_select", "_prev_scene_idx", "reader_page_idx",
              "_xlsx_sig", "_last_save_sig"):
        st.session_state.pop(k, None)

    st.session_state.project_rules = []
    st.session_state.custom_labels = []

    with st.spinner(f"Parsing {uploaded.name} …"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(uploaded.getvalue())
            tmp_path = f.name
        try:
            scenes, total_pages = parse_screenplay(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    rules = st.session_state.rules
    for scene in scenes:
        rec, conf = recommend_vp(scene.int_ext, scene.location, scene.time_of_day, rules)
        scene.recommendation = rec
        scene.confidence = conf

    st.session_state.scenes      = scenes
    st.session_state.total_pages = total_pages
    st.session_state.df = pd.DataFrame([
        {
            "Sc #":             s.number or str(i + 1),
            "Slug Line":        s.raw_slug,
            "INT/EXT":          s.int_ext,
            "Location":         s.location,
            "Time":             s.time_of_day,
            "Pages":            s.page_count_str,
            "Approach":         s.recommendation,
            "Confidence":       s.confidence,
            "VFX Notes":        "",
            "Production Notes": "",
        }
        for i, s in enumerate(scenes)
    ])

    for key in list(st.session_state.keys()):
        if key.startswith(("_rec_", "_vfx_", "_notes_", "_sol_", "_prev_approach_")):
            del st.session_state[key]

    saved = load_project(title_stem)
    if saved:
        st.session_state["_pending_restore"] = saved


# ── Guard: no script loaded ───────────────────────────────────────────────────

if st.session_state.df is None:
    _primary_tag = (
        f"<img src='{_PRIMARY_URI}' style='width:220px;object-fit:contain;margin-bottom:8px'>"
    ) if _PRIMARY_URI else (
        "<div style='font-size:0.8rem;color:#8ABAC8;letter-spacing:0.12em'>LUMOSTAGE</div>"
    )
    st.markdown(
        f"<div style='max-width:480px;padding:40px 0 20px 0'>"
        f"{_primary_tag}"
        f"<div class='slugger-word' style='margin:12px 0 6px 0'>"
        f"<span class='glove'>🥊</span>SLUGGER</div>"
        f"<div style='font-size:0.9rem;color:#8ABAC8;font-style:italic;margin-bottom:24px'>"
        f"Taking the mental out of breakdowns</div>"
        f"<div style='font-size:0.85rem;color:#C8D8E0'>"
        f"Upload a PDF screenplay in the sidebar to begin.</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.stop()


# ── Restore banner ────────────────────────────────────────────────────────────

if "_pending_restore" in st.session_state:
    saved_data = st.session_state["_pending_restore"]
    saved_at   = saved_data.get("saved_at", "unknown time")
    st.info(
        f"A saved session exists for **{st.session_state.script_title}** "
        f"(last saved {saved_at}). Restore it?"
    )
    col_yes, col_no, _ = st.columns([1, 1, 6])
    with col_yes:
        if st.button("Restore", type="primary", key="btn_restore_yes"):
            n = apply_save_to_scenes(st.session_state.scenes, saved_data)
            st.session_state.project_rules = saved_data.get("project_rules", [])
            st.session_state.custom_labels = saved_data.get("custom_labels", [])
            for key in list(st.session_state.keys()):
                if key.startswith(("_rec_", "_vfx_", "_notes_", "_sol_", "_prev_approach_")):
                    del st.session_state[key]
            del st.session_state["_pending_restore"]
            st.success(f"Restored {n} scenes.")
            st.rerun()
    with col_no:
        if st.button("Start fresh", key="btn_restore_no"):
            del st.session_state["_pending_restore"]
            st.rerun()


# ── Main data setup + shared summary ─────────────────────────────────────────

scenes      = st.session_state.scenes
df          = st.session_state.df
title       = st.session_state.script_title
total_pages = st.session_state.total_pages
pdf_bytes   = st.session_state.pdf_bytes

_summary: dict[str, dict] = defaultdict(lambda: {"scenes": 0, "pages": 0.0})
_total_pages_f = sum(_eighths_to_float(s.page_count_str) for s in scenes)

for _s in scenes:
    _k = _s.recommendation if isinstance(_s.recommendation, str) and _s.recommendation else "Unassigned"
    _summary[_k]["scenes"] += 1
    _summary[_k]["pages"]  += _eighths_to_float(_s.page_count_str)

_lumo_scenes = sum(v["scenes"] for k, v in _summary.items() if k in _LUMO_NAMES)
_lumo_pages  = sum(v["pages"]  for k, v in _summary.items() if k in _LUMO_NAMES)
_lumo_pct    = int(_lumo_pages / _total_pages_f * 100) if _total_pages_f else 0

# Stacked bar + legend for banner
_banner_bar_segs = ""
_banner_legend   = ""
for _a in _APPROACH_DISPLAY_ORDER + sorted(k for k in _summary if k not in _APPROACH_DISPLAY_ORDER):
    if _a not in _summary:
        continue
    _pgs   = _summary[_a]["pages"]
    _pct_f = (_pgs / _total_pages_f * 100) if _total_pages_f else 0
    if _pct_f < 1:
        continue
    _col = _APPROACH_COLOURS.get(_a, "555555")
    _banner_bar_segs += f"<div style='flex:{_pct_f:.1f};background:#{_col};opacity:0.9'></div>"
    if _pct_f >= 2:
        _banner_legend += (
            f"<div class='abl-item'>"
            f"<div class='abl-dot' style='background:#{_col}'></div>"
            f"<span>{_a}&nbsp;{_pct_f:.0f}%</span>"
            f"</div>"
        )

# ── Header banner ─────────────────────────────────────────────────────────────

_title_display = title.replace("-", " ").replace("_", " ")

st.markdown(
    f"<div class='script-banner'>"
    f"<div class='banner-title'>{_title_display[:60]}</div>"
    f"<div class='banner-sub'>Screenplay &nbsp;·&nbsp; {total_pages} pages &nbsp;·&nbsp; "
    f"{len(scenes)} scenes</div>"
    f"<div class='banner-pills'>"
    f"<div class='b-pill'><span class='b-pill-num'>{len(scenes)}</span>"
    f"<span class='b-pill-label'>Scenes</span></div>"
    f"<div class='b-pill'><span class='b-pill-num'>{total_pages}</span>"
    f"<span class='b-pill-label'>Pages</span></div>"
    f"<div class='b-pill'><span class='b-pill-num accent'>{_lumo_pct}%</span>"
    f"<span class='b-pill-label'>Lumostage</span></div>"
    f"<div class='b-pill'><span class='b-pill-num accent'>{_lumo_scenes}</span>"
    f"<span class='b-pill-label'>Lumo Scenes</span></div>"
    f"<div class='b-pill'><span class='b-pill-num'>"
    f"{rule_stats(st.session_state.rules)['total']}</span>"
    f"<span class='b-pill-label'>Learned Rules</span></div>"
    f"</div>"
    f"<div class='approach-bar'>{_banner_bar_segs}</div>"
    f"<div class='approach-bar-legend'>{_banner_legend}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

gaps = _scene_gaps(scenes)
if gaps:
    gap_str = ", ".join(str(g) for g in gaps[:30])
    suffix = f"  …and {len(gaps) - 30} more" if len(gaps) > 30 else ""
    st.warning(
        f"**Scene number gap detected** — scenes **{gap_str}**{suffix} appear to be missing. "
        f"Use **Add Missing Scene** in the Reader tab to insert them manually.",
        icon="⚠️",
    )


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_reader, tab_breakdown, tab_location, tab_chars, tab_options, tab_help = st.tabs([
    "Reader", "Scene Breakdown", "By Location", "Characters", "Options", "Help"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: READER
# ══════════════════════════════════════════════════════════════════════════════

with tab_reader:

    n_scenes = len(scenes)

    if "scene_jump_select" not in st.session_state:
        st.session_state["scene_jump_select"] = 0
    if "reader_page_idx" not in st.session_state:
        st.session_state["reader_page_idx"] = 0
    if "_prev_scene_idx" not in st.session_state:
        st.session_state["_prev_scene_idx"] = 0

    nav_prev, nav_select, nav_next = st.columns([1, 5, 1])
    with nav_prev:
        if st.button("◀ Prev", use_container_width=True, key="btn_prev_scene"):
            if st.session_state["scene_jump_select"] > 0:
                st.session_state["scene_jump_select"] -= 1
    with nav_next:
        if st.button("Next ▶", use_container_width=True, key="btn_next_scene"):
            if st.session_state["scene_jump_select"] < n_scenes - 1:
                st.session_state["scene_jump_select"] += 1
    with nav_select:
        scene_labels = [f"Sc {s.number}  —  {s.raw_slug[:60]}" for s in scenes]
        st.selectbox(
            "Jump to scene", options=range(n_scenes),
            format_func=lambda i: scene_labels[i],
            key="scene_jump_select", label_visibility="collapsed",
        )

    scene_idx = st.session_state["scene_jump_select"]
    scene     = scenes[scene_idx]

    if scene_idx != st.session_state["_prev_scene_idx"]:
        if not getattr(scene, "manually_added", False):
            st.session_state["reader_page_idx"] = int(scene.page_start)
        st.session_state["_prev_scene_idx"] = scene_idx

    page_idx = max(0, min(st.session_state["reader_page_idx"], total_pages - 1))

    st.divider()
    col_pdf, col_notes = st.columns([6, 4], gap="medium")

    with col_pdf:
        if getattr(scene, "manually_added", False):
            st.info("This scene was added manually — no PDF page position is known.")
        elif pdf_bytes:
            with st.spinner("Rendering page…"):
                png = render_page(pdf_bytes, page_idx)
            st.image(png, use_container_width=True)
        else:
            st.info("PDF not available for rendering.")

        pg_prev, pg_label, pg_next = st.columns([1, 4, 1])
        with pg_prev:
            if st.button("◀", key="btn_prev_page", use_container_width=True):
                if st.session_state["reader_page_idx"] > 0:
                    st.session_state["reader_page_idx"] -= 1
        with pg_next:
            if st.button("▶", key="btn_next_page", use_container_width=True):
                if st.session_state["reader_page_idx"] < total_pages - 1:
                    st.session_state["reader_page_idx"] += 1
        with pg_label:
            st.markdown(
                f"<p style='text-align:center;margin-top:6px;color:#555;font-size:0.85rem'>"
                f"Page {page_idx + 1} of {total_pages}</p>",
                unsafe_allow_html=True,
            )

    with col_notes:
        st.markdown(
            f"<p style='color:#888;font-size:0.8rem;margin-bottom:4px'>"
            f"Scene {scene_idx + 1} of {n_scenes}"
            + ("&nbsp;·&nbsp;<span style='color:#f57c00'>manually added</span>"
               if getattr(scene, "manually_added", False) else "")
            + "</p>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='scene-slug'>{scene.raw_slug}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p class='scene-meta'>{scene.int_ext} &nbsp;·&nbsp; "
            f"{scene.time_of_day} &nbsp;·&nbsp; {scene.page_count_str} pages</p>",
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Approach selector ─────────────────────────────────────────────────
        rec_key          = f"_rec_{scene_idx}"
        prev_approach_key = f"_prev_approach_{scene_idx}"

        if rec_key not in st.session_state:
            st.session_state[rec_key] = scene.recommendation

        new_rec = st.selectbox("Approach", _options(), key=rec_key)
        scene.recommendation = new_rec

        conf_colour = {
            "learned": "#2e7d32", "learned (similar)": "#558b2f",
            "high": "#1565c0", "medium": "#f57c00", "low": "#9e9e9e",
        }.get(scene.confidence, "#9e9e9e")
        st.markdown(
            f"<p style='font-size:0.75rem;color:{conf_colour};margin-top:-8px'>"
            f"confidence: {scene.confidence}</p>",
            unsafe_allow_html=True,
        )

        # ── Volume solutions ──────────────────────────────────────────────────
        _ac_live = st.session_state["approach_config"]
        _sols    = get_solutions(_ac_live)

        if _sols and new_rec:
            # Reset solutions when approach changes
            if st.session_state.get(prev_approach_key) is not None \
                    and st.session_state.get(prev_approach_key) != new_rec:
                scene.volume_solutions = {}
                for _s in _sols:
                    st.session_state.pop(f"_sol_{scene_idx}_{_sk(_s)}", None)
            st.session_state[prev_approach_key] = new_rec

            # Populate from defaults if empty
            if not scene.volume_solutions:
                scene.volume_solutions = default_solutions_for(_ac_live, new_rec)

            st.markdown("<div class='vol-sol-label'>Volume Solution</div>", unsafe_allow_html=True)
            sol_cols = st.columns(len(_sols))
            for _ci, _s in enumerate(_sols):
                _skey = f"_sol_{scene_idx}_{_sk(_s)}"
                if _skey not in st.session_state:
                    st.session_state[_skey] = scene.volume_solutions.get(_s, False)
                with sol_cols[_ci]:
                    _val = st.checkbox(
                        _SOL_ABBREV.get(_s, _s[:7]),
                        key=_skey,
                        help=_s,
                    )
                    scene.volume_solutions[_s] = _val

        # ── Notes ─────────────────────────────────────────────────────────────
        vfx_key = f"_vfx_{scene_idx}"
        if vfx_key not in st.session_state:
            st.session_state[vfx_key] = scene.vfx_notes
        scene.vfx_notes = st.text_area(
            "VFX Notes", key=vfx_key, height=80,
            placeholder="VFX requirements, asset notes…",
        )

        notes_key = f"_notes_{scene_idx}"
        if notes_key not in st.session_state:
            st.session_state[notes_key] = scene.production_notes
        scene.production_notes = st.text_area(
            "Production Notes", key=notes_key, height=100,
            placeholder="Set build, scheduling, location scouting…",
        )

        st.divider()

        if scene.characters:
            st.caption("**Characters:** " + "  ·  ".join(scene.characters))
        if scene.description:
            st.caption(scene.description[:220])

        same_page = [s for s in scenes if int(s.page_start) == page_idx and s is not scene]
        if same_page:
            st.divider()
            st.caption(f"**Also on page {page_idx + 1}:**")
            for s in same_page:
                st.caption(f"  Sc {s.number}: {s.raw_slug[:55]}")

        st.divider()
        _xlsx_sig = ";".join(
            f"{s.number}|{s.recommendation}|{s.vfx_notes}|{s.production_notes}"
            for s in scenes
        )
        if st.session_state.get("_xlsx_sig") != _xlsx_sig:
            st.session_state["_xlsx_sig"]   = _xlsx_sig
            st.session_state["_xlsx_bytes"] = export_to_excel(scenes, title)
        st.download_button(
            "Export to Excel",
            data=st.session_state["_xlsx_bytes"],
            file_name=f"{title}_breakdown.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="export_reader",
        )

        # ── Add Missing Scene ─────────────────────────────────────────────────
        if gaps:
            st.divider()
        with st.expander("➕ Add Missing Scene Manually", expanded=bool(gaps)):
            _gap_hint = str(gaps[0]) if gaps else ""
            with st.form("add_scene_form", clear_on_submit=True):
                col_n, col_ie, col_tod = st.columns([1, 1, 2])
                with col_n:
                    add_num = st.text_input("Scene #", value=_gap_hint, placeholder="5")
                with col_ie:
                    add_ie = st.selectbox("INT/EXT", ["INT", "EXT", "INT/EXT"])
                with col_tod:
                    add_tod = st.text_input("Time of Day", placeholder="DAY")
                add_loc = st.text_input("Location", placeholder="HIGH SCHOOL - CAFETERIA")
                add_rec = st.selectbox("Approach", _options())
                add_notes = st.text_input("Production Notes (optional)", placeholder="")
                submitted = st.form_submit_button("Add Scene", type="primary")

            if submitted:
                if add_num.strip() and add_loc.strip():
                    loc_clean = add_loc.upper().strip()
                    tod_clean = (add_tod or "DAY").upper().strip()
                    raw_slug  = f"{add_ie}. {loc_clean} - {tod_clean}"
                    new_scene = Scene(
                        number=add_num.strip(),
                        int_ext=add_ie,
                        location=loc_clean,
                        time_of_day=tod_clean,
                        raw_slug=raw_slug,
                        page_start=0.0,
                        page_count_str="?",
                        recommendation=add_rec,
                        confidence="manual",
                        production_notes=add_notes.strip(),
                        manually_added=True,
                    )
                    _insert_scene_sorted(st.session_state.scenes, new_scene)
                    st.session_state.pop("_xlsx_sig", None)
                    st.success(f"Scene {add_num.strip()} added.")
                    st.rerun()
                else:
                    st.error("Scene # and Location are required.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: SCENE BREAKDOWN
# ══════════════════════════════════════════════════════════════════════════════

with tab_breakdown:
    st.caption(
        "Edit **Approach**, **VFX Notes**, and **Production Notes** inline. "
        "Click **Save & Learn** to store your VP preferences."
    )

    # ── Approach Summary ──────────────────────────────────────────────────────

    def _pct(pages: float) -> str:
        if _total_pages_f <= 0:
            return "—"
        return f"{pages / _total_pages_f * 100:.0f}%"

    def _row_class(approach: str) -> str:
        if approach in _LUMO_NAMES:  return "lumo"
        if approach in (R_VFX,):     return "vfx"
        if approach in (R_EITHER,):  return "either"
        return "loc"

    _bd_display = [k for k in _APPROACH_DISPLAY_ORDER if k in _summary] + \
                  sorted(k for k in _summary if k not in _APPROACH_DISPLAY_ORDER)

    rows_html = ""
    for approach in _bd_display:
        d = _summary[approach]
        cls = _row_class(approach)
        _dot_col = _APPROACH_COLOURS.get(approach, "555555")
        rows_html += (
            f"<div class='as-row'>"
            f"<span class='as-label {cls}'>"
            f"<span style='display:inline-block;width:8px;height:8px;border-radius:2px;"
            f"background:#{_dot_col};margin-right:7px;vertical-align:middle'></span>"
            f"{approach}</span>"
            f"<span class='as-num'>{d['scenes']}</span>"
            f"<span class='as-num'>{_eighths_str_from_float(d['pages'])}</span>"
            f"<span class='as-num'>{_pct(d['pages'])}</span>"
            f"</div>"
        )

    summary_html = f"""
<div class='approach-summary'>
  <h4>Approach Summary</h4>
  <div class='as-col-headers'>
    <span>Approach</span><span>Scenes</span><span>Pages (1/8)</span><span>% Script</span>
  </div>
  {rows_html}
  <hr class='as-divider'>
  <div class='as-row'>
    <span class='as-label total'>Lumostage Total</span>
    <span class='as-num total'>{_lumo_scenes}</span>
    <span class='as-num total'>{_eighths_str_from_float(_lumo_pages)}</span>
    <span class='as-num total'>{_pct(_lumo_pages)}</span>
  </div>
</div>
"""
    st.markdown(summary_html, unsafe_allow_html=True)

    live_df = pd.DataFrame([
        {
            "Sc #":             s.number or str(i + 1),
            "Slug Line":        s.raw_slug,
            "INT/EXT":          s.int_ext,
            "Location":         s.location,
            "Time":             s.time_of_day,
            "Pages":            s.page_count_str,
            "Approach":         s.recommendation,
            "Confidence":       s.confidence,
            "VFX Notes":        s.vfx_notes,
            "Production Notes": s.production_notes,
        }
        for i, s in enumerate(scenes)
    ])

    edited_df = st.data_editor(
        live_df,
        column_config={
            "Sc #":      st.column_config.TextColumn("Sc #", width="small"),
            "Slug Line": st.column_config.TextColumn("Slug Line", width="large"),
            "INT/EXT":   st.column_config.TextColumn("INT/EXT", width="small"),
            "Location":  st.column_config.TextColumn("Location", width="medium"),
            "Time":      st.column_config.TextColumn("Time", width="small"),
            "Pages":     st.column_config.TextColumn("Pages", width="small"),
            "Approach":  st.column_config.SelectboxColumn("Approach", options=_options(), width="medium"),
            "Confidence": st.column_config.TextColumn("Confidence", width="small", disabled=True),
            "VFX Notes":        st.column_config.TextColumn("VFX Notes", width="medium"),
            "Production Notes": st.column_config.TextColumn("Production Notes", width="large"),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="breakdown_editor",
    )

    for i, row in edited_df.iterrows():
        if i < len(scenes):
            _rec = row["Approach"]
            scenes[i].recommendation   = _rec if isinstance(_rec, str) else ""
            scenes[i].vfx_notes        = row["VFX Notes"] or ""
            scenes[i].production_notes = row["Production Notes"] or ""

    btn_l, btn_r = st.columns([2, 2])
    with btn_l:
        if st.button("Save & Learn", type="primary", use_container_width=True):
            rows = edited_df.to_dict("records")
            st.session_state.rules = learn_from_edits(rows, st.session_state.rules)
            st.success(f"Saved. {rule_stats(st.session_state.rules)['total']} location rules stored.")
    with btn_r:
        _xlsx_sig = ";".join(
            f"{s.number}|{s.recommendation}|{s.vfx_notes}|{s.production_notes}"
            for s in scenes
        )
        if st.session_state.get("_xlsx_sig") != _xlsx_sig:
            st.session_state["_xlsx_sig"]   = _xlsx_sig
            st.session_state["_xlsx_bytes"] = export_to_excel(scenes, title)
        st.download_button(
            "Export to Excel",
            data=st.session_state["_xlsx_bytes"],
            file_name=f"{title}_breakdown.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="export_breakdown",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: BY LOCATION
# ══════════════════════════════════════════════════════════════════════════════

with tab_location:
    groups: dict[str, list] = defaultdict(list)
    for s in scenes:
        root = s.location.split(" - ")[0].strip()
        groups[root].append(s)

    st.caption(f"{len(groups)} unique root locations · {len(scenes)} total scenes.")

    for root_loc in sorted(groups.keys()):
        loc_scenes = groups[root_loc]
        total_p = sum(_eighths_to_float(s.page_count_str) for s in loc_scenes)
        label = (
            f"**{root_loc}** — {len(loc_scenes)} scene{'s' if len(loc_scenes) != 1 else ''}, "
            f"{_eighths_str_from_float(total_p)} pages"
        )
        with st.expander(label, expanded=False):
            st.dataframe(pd.DataFrame([
                {"Sc #": s.number, "Slug Line": s.raw_slug, "Pages": s.page_count_str, "Approach": s.recommendation}
                for s in loc_scenes
            ]), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: CHARACTERS
# ══════════════════════════════════════════════════════════════════════════════

with tab_chars:
    char_counts: Counter = Counter()
    char_scenes_map: dict[str, list[str]] = defaultdict(list)
    for s in scenes:
        for c in s.characters:
            char_counts[c] += 1
            char_scenes_map[c].append(s.number or "?")

    if char_counts:
        char_df = pd.DataFrame([
            {"Character": c, "Scenes": n, "Scene Numbers": ", ".join(char_scenes_map[c])}
            for c, n in char_counts.most_common()
        ])
        st.caption(f"{len(char_counts)} characters detected. (Heuristic — review for false positives.)")
        st.dataframe(char_df, use_container_width=True, hide_index=True)
    else:
        st.info("No characters detected for this script.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

with tab_options:

    # ── Save / Load ───────────────────────────────────────────────────────────
    st.subheader("Save / Load Project")
    col_save, _ = st.columns([2, 4])
    with col_save:
        if st.button("💾 Save Now", use_container_width=True, key="btn_manual_save"):
            path = save_project(
                title, scenes,
                st.session_state.get("project_rules", []),
                st.session_state.get("custom_labels", []),
            )
            st.success(f"Saved to {path.name}")

    saves = list_saves()
    if saves:
        st.caption(f"{len(saves)} saved project(s) on disk:")
        for p in saves[:10]:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            marker = " ◀ current" if p.stem == title else ""
            st.caption(f"  **{p.stem}** — {mtime}{marker}")

    st.divider()

    # ── Import from Excel ─────────────────────────────────────────────────────
    st.subheader("Import from Excel")
    st.caption(
        "Upload a previously exported breakdown xlsx to pull in Approach, VFX Notes, "
        "and Production Notes. Scenes are matched by scene number."
    )
    xlsx_upload = st.file_uploader("Upload breakdown xlsx", type=["xlsx"],
                                   key="xlsx_import_uploader")
    if xlsx_upload:
        _import_data, _import_err = import_from_excel(xlsx_upload.getvalue())
        if _import_err:
            st.error(_import_err)
        elif not _import_data:
            st.warning("No scene rows found in the uploaded file.")
        else:
            _valid_opts = _options()
            _preview_rows = []
            _scene_map = {s.number: s for s in scenes if s.number}
            for _num, _row in sorted(_import_data.items(), key=lambda x: (len(x[0]), x[0])):
                _sc = _scene_map.get(_num)
                if _sc is None:
                    continue
                _rec_new   = _row.get("recommendation", "")
                _vfx_new   = _row.get("vfx_notes", "")
                _notes_new = _row.get("production_notes", "")
                _rec_ok    = _rec_new and _rec_new in _valid_opts
                _changes   = []
                if _rec_ok and _rec_new != _sc.recommendation:
                    _changes.append(f"Approach: {_sc.recommendation!r} → {_rec_new!r}")
                if _vfx_new and _vfx_new != _sc.vfx_notes:
                    _changes.append("VFX notes updated")
                if _notes_new and _notes_new != _sc.production_notes:
                    _changes.append("Production notes updated")
                if _changes:
                    _preview_rows.append({"Sc #": _num, "Slug": _sc.raw_slug[:50], "Changes": " · ".join(_changes)})

            if _preview_rows:
                st.caption(f"**{len(_preview_rows)} scene(s) will be updated:**")
                st.dataframe(pd.DataFrame(_preview_rows), use_container_width=True, hide_index=True)
                if st.button("Apply Import", type="primary", key="btn_apply_xlsx_import"):
                    _n = apply_excel_import(scenes, _import_data, _valid_opts)
                    for _key in list(st.session_state.keys()):
                        if _key.startswith(("_rec_", "_vfx_", "_notes_", "_sol_", "_prev_approach_")):
                            del st.session_state[_key]
                    st.session_state.pop("_xlsx_sig", None)
                    st.success(f"Imported — {_n} scene(s) updated.")
                    st.rerun()
            else:
                st.info("No differences found — the uploaded file matches the current breakdown.")

    st.divider()

    # ── Project-Specific Rules ────────────────────────────────────────────────
    st.subheader("Project-Specific Rules")
    st.caption(
        "These rules override the global heuristics for this project only. "
        "First matching rule per scene wins."
    )
    current_rules = st.session_state.get("project_rules", [])
    rules_seed    = current_rules if current_rules else [{"int_ext": "BOTH", "keyword": "", "approach": ""}]
    edited_rules  = st.data_editor(
        pd.DataFrame(rules_seed),
        column_config={
            "int_ext":  st.column_config.SelectboxColumn("INT/EXT", options=["INT", "EXT", "BOTH"], width="small"),
            "keyword":  st.column_config.TextColumn("Location Keyword", width="medium"),
            "approach": st.column_config.SelectboxColumn("Approach", options=_options(), width="medium"),
        },
        use_container_width=True, hide_index=True, num_rows="dynamic",
        key="project_rules_editor",
    )
    new_rules = [
        r for r in edited_rules.to_dict("records")
        if r.get("keyword", "").strip() and r.get("approach", "").strip()
    ]
    st.session_state.project_rules = new_rules

    if st.button("Apply Rules to All Scenes", type="primary", key="btn_apply_rules"):
        n_changed = apply_project_rules(scenes, new_rules)
        for key in list(st.session_state.keys()):
            if key.startswith("_rec_"):
                del st.session_state[key]
        st.session_state.pop("_xlsx_sig", None)
        st.success(f"Applied — {n_changed} scene(s) updated.")
        st.rerun()

    st.divider()

    # ── Approach Configuration ────────────────────────────────────────────────
    st.subheader("Approach Configuration")
    st.caption(
        "Edit which approaches count toward the Lumostage total and their default "
        "volume solution checkboxes. Add new approaches as your gag library grows."
    )

    _ac_edit = st.session_state["approach_config"]
    _sols_edit = get_solutions(_ac_edit)

    # Build editable dataframe
    _config_rows = []
    for _a in _ac_edit.get("approaches", []):
        _row = {
            "Approach":  _a["name"],
            "Lumostage": _a.get("lumo") == "YES",
        }
        for _s in _sols_edit:
            _row[_s] = bool(_a.get("solutions", {}).get(_s, False))
        _config_rows.append(_row)

    _col_config = {
        "Approach":  st.column_config.TextColumn("Approach", width="medium"),
        "Lumostage": st.column_config.CheckboxColumn("Lumostage", width="small"),
    }
    for _s in _sols_edit:
        _col_config[_s] = st.column_config.CheckboxColumn(_SOL_ABBREV.get(_s, _s[:8]), width="small", help=_s)

    _edited_config = st.data_editor(
        pd.DataFrame(_config_rows),
        column_config=_col_config,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="approach_config_editor",
    )

    if st.button("Save Approach Config", type="primary", key="btn_save_approach_config"):
        _new_approaches = []
        for _, _row in _edited_config.iterrows():
            _name = str(_row.get("Approach", "")).strip()
            if not _name:
                continue
            _existing = get_approach_def(_ac_edit, _name)
            _new_approaches.append({
                "name":    _name,
                "lumo":    "YES" if _row.get("Lumostage") else "NO",
                "colour":  _existing.get("colour", "555555") if _existing else "555555",
                "solutions": {_s: bool(_row.get(_s, False)) for _s in _sols_edit},
            })
        _ac_edit["approaches"] = _new_approaches
        save_config(_ac_edit)
        st.session_state["approach_config"] = load_config()
        st.success("Approach configuration saved.")
        st.rerun()

    st.divider()

    # ── Add Solution Type ─────────────────────────────────────────────────────
    st.subheader("Solution Types")
    st.caption("The column headings for volume solution checkboxes. Add new types as needed.")

    for _s in _sols_edit:
        st.caption(f"· {_s}")

    _col_sol, _col_sol_add = st.columns([4, 1])
    with _col_sol:
        _new_sol = st.text_input(
            "New solution type", placeholder="e.g. MINIATURE",
            key="new_sol_input", label_visibility="collapsed",
        )
    with _col_sol_add:
        if st.button("Add", key="btn_add_sol", use_container_width=True):
            _ns = _new_sol.strip().upper()
            if _ns and _ns not in _sols_edit:
                _ac_edit["solutions"].append(_ns)
                for _ap in _ac_edit.get("approaches", []):
                    _ap.setdefault("solutions", {})[_ns] = False
                save_config(_ac_edit)
                st.session_state["approach_config"] = load_config()
                st.success(f"Added solution type: {_ns}")
                st.rerun()
            elif _ns in _sols_edit:
                st.warning("Already exists.")

    st.divider()

    # ── Custom Approach Labels (per-project) ──────────────────────────────────
    st.subheader("Project-Specific Approach Labels")
    st.caption("Extra labels for this project only, in addition to the global approach list.")

    custom = list(st.session_state.get("custom_labels", []))
    _base  = get_approach_names(st.session_state["approach_config"])
    col_input, col_add = st.columns([4, 1])
    with col_input:
        new_label = st.text_input(
            "New label", placeholder="e.g. Practical + LED Hybrid",
            key="new_label_input", label_visibility="collapsed",
        )
    with col_add:
        if st.button("Add", key="btn_add_label", use_container_width=True):
            if new_label.strip():
                label = new_label.strip()
                if label not in custom and label not in _base:
                    st.session_state.custom_labels = custom + [label]
                    st.rerun()
                else:
                    st.warning("Label already exists.")

    if custom:
        for i, lbl in enumerate(custom):
            col_l, col_r = st.columns([5, 1])
            col_l.markdown(f"· **{lbl}**")
            if col_r.button("✕", key=f"rm_label_{i}", use_container_width=True):
                st.session_state.custom_labels = [x for x in custom if x != lbl]
                st.rerun()
    else:
        st.caption("No project-specific labels yet.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: HELP
# ══════════════════════════════════════════════════════════════════════════════

with tab_help:
    st.markdown("""
### Approach hierarchy

Approaches are grouped by Lumostage status. **Lumostage Total** (shown in the
Scene Breakdown summary and the header banner) is the sum of all approaches
marked **Lumostage = YES** in Options → Approach Configuration.

| Approach | Lumostage |
|---|---|
| VPROD | YES — full virtual production on the volume |
| INT. CAR | YES — vehicle interior rig |
| HYBRID VIRTUAL | YES — partial LED / set build hybrid |
| INT. SUBWAY TRAIN | YES — subway car gag |
| INT. PLATFORM | YES — platform gag |
| EXT. ROOFTOP | YES — rooftop gag |
| EXT. DESERT | YES — desert/landscape gag |
| INT. PLANE | NO |
| EITHER | NO |
| LOCATION | NO |
| STUDIO | NO |
| VFX | NO |
| OMITTED | NO |

### Volume Solutions

In the **Reader** tab, selecting an Approach shows pre-checked volume solution
checkboxes (VAD, UNREAL, PRACT., VFX PLT, SET BLD). Defaults come from
**Options → Approach Configuration**. Changing the Approach resets the
checkboxes to the new defaults; you can then override individually.

### VP Recommendation Logic

| Trigger | Recommendation |
|---|---|
| INT. + car / truck / van / limo … | INT. CAR |
| EXT. + desert / canyon / badlands … | EXT. DESERT |
| EXT. + rooftop / roof terrace … | EXT. ROOFTOP |
| Distant city / INT. | VPROD |
| Distant EXT. with crowds | LOCATION |
| INT. + subway / metro / rail car … | INT. SUBWAY TRAIN |
| INT. + platform … | INT. PLATFORM |
| Any + airplane / helicopter / yacht … | INT. PLANE |
| Fantastical, period, impossible | VPROD |
| Dangerous (cliff edge, combat zone …) | VPROD |
| Extreme environments (morgue, bunker …) | VPROD |
| Common local EXT. | LOCATION |
| Generic INT. | EITHER |

### Learning

Edit **Approach** in the Reader or Scene Breakdown table, then click
**Save & Learn** to store your choice globally. The same location string on
any future script will use your stored recommendation.

### Auto-save

Your breakdown saves automatically whenever Approach or notes change.
Upload the same PDF again to be offered a restore.
""")


# ── Auto-save ─────────────────────────────────────────────────────────────────

_auto_sig = ";".join(
    f"{s.number}|{s.recommendation}|{s.vfx_notes}|{s.production_notes}"
    f"|{json.dumps(getattr(s, 'volume_solutions', {}), sort_keys=True)}"
    for s in scenes
)
if st.session_state.get("_last_save_sig") != _auto_sig:
    st.session_state["_last_save_sig"] = _auto_sig
    save_project(
        title, scenes,
        st.session_state.get("project_rules", []),
        st.session_state.get("custom_labels", []),
    )
