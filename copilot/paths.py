"""Where Galley's files live.

RES  - read-only program files: indesign/*.jsx, ingest/, ui/, style/, art/, samples/.
       In development: the project folder. In the installed app: the bundle PyInstaller unpacked.
DATA - the user's work: work/ (manuscripts, references, content.json, reports) and out/ (builds).
       In development: the project folder, as before. Installed: the user's profile, so an update
       (which replaces the program files) never touches it:
         Windows  %APPDATA%\\Galley
         macOS    ~/Library/Application Support/Galley
       GALLEY_DATA overrides both.
"""
import os
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = getattr(sys, '_MEIPASS', REPO) if FROZEN else REPO


def _profile_dir():
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Galley')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Galley')
    return os.path.join(os.path.expanduser('~'), '.galley')


DATA = os.environ.get('GALLEY_DATA') or (_profile_dir() if FROZEN else REPO)
WORK = os.path.join(DATA, 'work')
OUT = os.path.join(DATA, 'out')
USER_STYLES = os.path.join(DATA, 'style')  # styles the user makes (e.g. custom.json); built-in ones stay in RES/style
PORT = int(os.environ.get('GALLEY_PORT', '8765'))


def version():
    v = os.environ.get('GALLEY_VERSION')
    if v:
        return v
    try:
        with open(os.path.join(RES, 'VERSION'), encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return 'dev'


for d in (WORK, OUT):
    os.makedirs(d, exist_ok=True)
