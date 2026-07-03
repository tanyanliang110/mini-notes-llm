# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\workplace\\anna\\mini-notes-llm\\executas\\summarize\\summarize_tool.py'],
    pathex=['D:\\workplace\\anna\\examples\\anna-executa-examples\\sdk\\python'],
    binaries=[],
    datas=[],
    hiddenimports=['executa_sdk', 'executa_sdk.sampling', 'executa_sdk.storage'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mini-notes-summarize.exe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
