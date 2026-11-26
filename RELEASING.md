# Releasing Galley (the desktop app) and pushing updates

Galley ships as a desktop app: an Electron window (the copilot, docked beside InDesign, in the tray) with
the Galley engine bundled inside it. Installed copies check for updates when they start and every 4 hours,
download a new version in the background and show **"Galley x.y.z is ready · Restart to update"** in the copilot.

```
Galley/
  desktop/            the Electron app: main.js (engine, window, tray, updates), preload.js, splash.html, assets/
  packaging/          galley-engine.spec (PyInstaller recipe for the engine)
  dist/galley-engine  the built engine (made by step 2, bundled into the app by step 3)
  desktop/dist        installers and update files (made by step 3)
```

## One-time setup
1. Node.js (18+) and Python 3 with `pip install -r requirements.txt pyinstaller`.
2. `cd desktop && npm install`.
3. **Where updates are published.** The source repository (`tosin25/galli`) is private, and installed apps
   cannot read a private repository without a password, so publish the app to a separate **public**
   repository that holds only installers: create `tosin25/galley-releases` (public, empty). The app is already
   set to look there (`desktop/package.json` > `build.publish`).
4. A GitHub token that may write to that repository (GitHub > Settings > Developer settings > Fine-grained
   tokens > only `galley-releases`, permission *Contents: read and write*). Keep it out of the repository:
   set it in the terminal when releasing (`$env:GH_TOKEN = "..."` in PowerShell).

## Every release
1. Raise the version in **two** places: `desktop/package.json` (`"version"`) and `VERSION` (e.g. `0.3.1`).
2. Build the engine (picks up every change in ui/, indesign/, ingest/, copilot/, style/):
   ```
   cd desktop
   npm run engine
   ```
3. Build and publish the installer:
   ```
   npm run release        # builds desktop/dist/Galley-Setup-x.y.z.exe + latest.yml and uploads them as a GitHub release
   ```
   (`npm run dist` builds without uploading, for testing.)
4. On GitHub, open the new draft release in `galley-releases` and press **Publish release**. Installed copies
   pick it up within 4 hours, or straight away from the tray: **Check for updates**.

## Installing on a designer's laptop (first time only)
Send them `Galley-Setup-x.y.z.exe` (or the release page link). They double-click it; Galley installs for that
user (no admin needed), starts, and appears on the right of the screen and in the tray. After that, updates
arrive by themselves.

## Things to know
- **Windows warning on first install.** The installer is not code-signed yet, so Windows SmartScreen says
  "Windows protected your PC": click *More info* > *Run anyway*. A code-signing certificate (about
  USD 200-400 a year) removes this; add it to `build.win` when you have one.
- **Mac.** The same app builds on a Mac (`npm run engine && npm run release` there) once the macOS InDesign
  bridge exists (see HANDOFF.md). Apple requires a Developer ID (USD 99 a year) and notarization for the app to
  open without warnings and for updates to install.
- **What updates replace.** Only the program. Each user's work, references, settings and API key live in
  `%APPDATA%\Galley` (Windows) / `~/Library/Application Support/Galley` (Mac) and are kept.
- **Testing an update without GitHub.** Build version A and install it; build version B into a folder; serve
  that folder (`python -m http.server 8800` inside `desktop/dist`) and start the installed app with
  `GALLEY_UPDATE_URL=http://127.0.0.1:8800`: it finds B, downloads it and offers the restart.
- **Logs** for support: `%APPDATA%\Galley\galley-engine.log` (engine) and `%APPDATA%\Galley\logs\main.log`
  (app, written by electron-log).
