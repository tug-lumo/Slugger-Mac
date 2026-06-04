# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

for pkg in ('streamlit', 'fitz', 'altair', 'pandas', 'openpyxl', 'rumps'):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# app.py must stay as a data file — Streamlit runs it as a script, not a module.
# All other local .py files are imported by launcher.py above, so PyInstaller
# compiles them into the archive automatically (no datas entry needed).
datas += [
    ('app.py',                                           '.'),
    ('data/vp_rules.json',                               'data'),
    ('data/approaches.json',                             'data'),
    ('.streamlit/config.toml',                           '.streamlit'),
    ('Lumostage_Emblem_RGB.png',                         '.'),
    ('Lumostage_Primary_FullColour_RGB--whitetext.png',  '.'),
]

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
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
    icon='slugger.icns',
    bundle_identifier='com.lumostage.slugger',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # hide Dock icon — lives in menu bar only
    },
)
