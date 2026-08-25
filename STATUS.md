# Screenplay Breakdown Tool — Project Status

_Last updated: 2026-06-02 (slug parser expanded + gap detection + manual scene add)_

---

## What this is

A fully local (no cloud, no AI calls) screenplay PDF reader and VP breakdown tool built for Lumostage. Parses PDFs — including watermarked drafts — extracts slug lines, auto-recommends a virtual production approach, and lets you review and edit the breakdown scene by scene alongside the actual script.

---

## Current state: complete and working

### Core features

| Feature | Status |
|---|---|
| PDF parsing (incl. watermarked drafts) | ✅ Font-level watermark filtering |
| Slug line extraction (INT./EXT., location, time) | ✅ Expanded TOD list + fallback regex + optional spacing |
| Sequential gap detection | ✅ Warning banner with missing scene numbers |
| Manual scene insertion | ✅ "Add Missing Scene" form in Scene Breakdown tab |
| Scene numbers, page counts in eighths | ✅ |
| VP auto-recommendation ("3 D's" framework) | ✅ See logic below |
| Side-by-side PDF reader + notes panel | ✅ |
| Editable breakdown table | ✅ |
| By Location rollup | ✅ |
| Character detection | ✅ Heuristic, needs review |
| Export to Excel (3 sheets) | ✅ Cached, only rebuilds on change |
| Learning system (stores manual corrections) | ✅ `data/vp_rules.json` |
| Auto-save (silent, signature-based) | ✅ `saves/{title}.json` |
| Restore previous session on upload | ✅ Banner prompt |
| Project-specific keyword rules | ✅ Options tab |
| Custom approach labels | ✅ Options tab |
| Cross-platform (Windows + Mac) | ✅ `run.bat` / `run.command` |
| Lumostage brand theme (dark, #13191A / seafoam / blue) | ✅ `.streamlit/config.toml` + CSS |
| Approach Summary panel (scenes, 1/8 pages, % script, VP total) | ✅ Scene Breakdown tab |

### VP recommendation priority order

1. Learned rules — exact match (from past manual corrections)
2. Learned rules — root location match
3. INT. road vehicle → `VP (INT. Vehicle)`
4. Distant city / landscape check (before transit, to catch e.g. NY SUBWAY)
   - Distant + INT. → `Lumostage`
   - Distant + EXT. + crowds/environment → `On Location`
   - Distant + EXT. contained → `Lumostage`
5. Local transit / moving vessels → `VP (INT. Aircraft)`
6. Doesn't Exist (fantastical, period, space, digital) → `Lumostage`
7. Dangerous (cliff edge, combat zone, extreme weather) → `Lumostage`
8. Strong Lumostage signals (morgue, bunker, server room, mountaintop) → `Lumostage`
9. Practical local EXT. → `On Location`
10. Generic INT. → `Option: Either`

VFX is a **manual-only** label — not auto-recommended. Lumostage is treated as a large-exterior locations solution, not just a small stage.

---

## File structure

```
screenplay_reader/
├── app.py                  Main Streamlit UI
├── screenplay_parser.py    PDF parsing, slug extraction, Scene dataclass
├── vp_heuristics.py        3D recommendation engine + learning system
├── exporter.py             Excel export (3 sheets, colour-coded)
├── project_state.py        Per-project save/load (saves/*.json)
├── requirements.txt        streamlit, pymupdf, openpyxl, pandas
├── run.bat                 Windows launcher (double-click)
├── run.command             Mac launcher (chmod +x first, then double-click)
├── data/
│   └── vp_rules.json       Learned location rules (persists across sessions)
└── saves/
    └── {title}.json        Per-project breakdown saves (auto + manual)
```

---

## Known limitations / watch list

- **Character detection** is heuristic (all-caps lines that aren't slugs or transitions). False positives likely on scripts with unusual formatting. A review pass is needed before using the Characters tab for scheduling.
- **Scene numbers** rely on left/right margin position. Scripts without printed scene numbers get sequential fallback numbers — these won't match the production's numbering if scenes are added/cut.
- **Page count** is estimated from slug line positions, not from formal A/B pages. Suitable for scheduling estimates, not locked-page reports.
- **Learned rules are global** — they apply across all projects. If the same location name means different things on different productions (e.g. "THE OFFICE"), a project-specific rule in the Options tab overrides it cleanly.
- **Mac first-run** requires `chmod +x run.command` in Terminal before Finder double-click works.

---

## Candidate next-phase features

### High value / likely needed soon

- **Re-parse with project rules pre-applied** — currently rules only apply after an initial parse. Could wire project rules into the initial recommend pass so the first result already reflects them.
- **Lock / approve scenes** — a "locked" flag per scene that prevents auto-save from overwriting a manually confirmed choice. Useful once the breakdown goes to production.
- **Notes export improvements** — add VFX Notes and Production Notes as separate columns in the By Location sheet (currently only in Scene Breakdown sheet).
- **Multi-script comparison** — load two saves side by side to compare approach changes across drafts (e.g. revision A vs B).

### Medium priority

- **Scene filter / search** — filter the breakdown table by Approach, INT/EXT, or location keyword without leaving the table view.
- ~~**Approach summary banner**~~ — implemented as a full panel in Scene Breakdown tab (scenes + 1/8 pages + % per approach, VP Process Total subtotal).
- **PDF annotation export** — write approach labels back onto the PDF as annotations, so the marked-up script can be shared with the director/line producer without needing the app.

### Longer term

- **Revision diff** — compare two versions of the same script, highlighting new/changed/deleted scenes and whether the approach recommendation changed.
- **Call sheet / stripboard CSV export** — export in a format compatible with Movie Magic or EP Scheduling for direct import.
- **Shared team mode** — lightweight multi-user: one person reads, another updates approaches, changes sync via a shared `saves/` folder on Dropbox/network drive.

---

## How to resume development

1. Read this file.
2. Read `app.py` — it's the UI entry point and references everything else.
3. `vp_heuristics.py` is where recommendation logic lives — most tuning happens here.
4. `screenplay_parser.py` is where parsing edge cases live — touch only if a script isn't parsing correctly.
5. Run `run.bat` (Windows) or `./run.command` (Mac) to start the dev server. Streamlit hot-reloads on file save.
