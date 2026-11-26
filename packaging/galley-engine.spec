# PyInstaller recipe for the Galley engine (the local server the desktop app talks to).
#   python -m PyInstaller packaging/galley-engine.spec --noconfirm
# -> dist/galley-engine/galley-engine(.exe), a folder with everything it needs (no Python on the user's machine).
# Build on each platform you ship (Windows here; macOS on a Mac).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))  # noqa: F821 - SPECPATH is provided by PyInstaller
DATA_DIRS = ['ui', 'style', 'art', 'samples', 'indesign', 'ingest']
datas = [(os.path.join(ROOT, d), d) for d in DATA_DIRS] + [(os.path.join(ROOT, 'VERSION'), '.')]

hidden = ['ingest', 'docx_parts', 'xml.etree.ElementTree', 'xml.sax.saxutils', 'zipfile', 'struct', 'anthropic']
if sys.platform == 'win32':
    hidden += ['pythoncom', 'pywintypes', 'win32com', 'win32com.client']

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, 'ui', 'server.py')],
    pathex=[ROOT, os.path.join(ROOT, 'ingest')],
    datas=datas,
    hiddenimports=hidden,
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='galley-engine',
    console=False,        # runs hidden inside the desktop app; output goes to galley-engine.log
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='galley-engine', upx=False)  # noqa: F821
