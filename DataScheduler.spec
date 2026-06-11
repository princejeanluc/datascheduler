# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — DataScheduler
# Génère : dist/DataScheduler/DataScheduler.exe (mode one-folder)

from PyInstaller.utils.hooks import collect_data_files, collect_all, collect_submodules

block_cipher = None

# oracledb : package avec extensions C + données internes
oracledb_datas, oracledb_binaries, oracledb_hidden = collect_all('oracledb')

# tzdata : base de données des fuseaux horaires (nécessaire sous Windows)
tzdata_datas, _, _ = collect_all('tzdata')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=oracledb_binaries,
    datas=oracledb_datas + tzdata_datas,
    hiddenimports=[
        # ── Modules applicatifs (déclarés explicitement pour PyInstaller) ──
        'database',
        'database.db_manager',
        'database.models',
        'core',
        'core.scheduler',
        'core.pipeline',
        'core.oracle',
        'core.ftp',
        'ui',
        'ui.main_window',
        'ui.dialogs',
        'ui.pipeline_dialog',
        'ui.styles',

        # ── oracledb (thin mode — pas de client Oracle requis) ──
        *oracledb_hidden,

        # ── SQLAlchemy ──
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.pysqlite',
        'sqlalchemy.ext.baked',
        'sqlalchemy.pool',

        # ── APScheduler ──
        *collect_submodules('apscheduler'),

        # ── Paramiko / cryptographie ──
        *collect_submodules('paramiko'),
        *collect_submodules('cryptography'),
        'bcrypt',
        'pynacl',

        # ── Fuseaux horaires ──
        'tzdata',
        'tzlocal',

        # ── Pandas / NumPy ──
        'pandas',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'tkinter',
        'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DataScheduler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # pas de fenêtre console (GUI pur)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # ajouter un .ico ici si disponible : icon='assets/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DataScheduler',
)
