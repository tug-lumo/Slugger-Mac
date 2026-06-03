# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

for pkg in ('streamlit', 'fitz', 'altair', 'pandas', 'openpyxl'):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

datas += [
    ('app.py',                                       '.'),
    ('screenplay_parser.py',                         '.'),
    ('vp_heuristics.py',                             '.'),
    ('exporter.py',                                  '.'),
    ('project_state.py',                             '.'),
    ('data/vp_rules.json',                           'data'),
    ('data/approaches.json',                         'data'),
    ('approach_config.py',                           '.'),
    ('.streamlit/config.toml',                       '.streamlit'),
    ('Lumostage_Emblem_RGB.png',                     '.'),
    ('Lumostage_Primary_FullColour_RGB--whitetext.png', '.'),
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Slugger',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='Slugger',
)

app = BUNDLE(
    coll,
    name='Slugger.app',
    bundle_identifier='com.lumostage.slugger',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
    },
)
