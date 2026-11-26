// Galley desktop app: starts the Galley engine (local server that drives InDesign), shows the copilot in a
// narrow window docked on the right and pinned above InDesign, lives in the tray, and updates itself.
const { app, BrowserWindow, Tray, Menu, screen, shell, ipcMain, nativeImage, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const log = require('electron-log');
const { autoUpdater } = require('electron-updater');

const PORT = Number(process.env.GALLEY_PORT || 8765);
const URL = `http://127.0.0.1:${PORT}`;
const WIDTH = 440;
log.transports.file.level = 'info';
autoUpdater.logger = log;

let win = null, tray = null, engine = null, quitting = false;
let indesignOpen = false, userHid = false;

// ---------------------------------------------------------------- preferences (kept in the user's profile)
const PREFS_FILE = () => path.join(app.getPath('userData'), 'galley-app.json');
const prefs = { pinned: true, followInDesign: true, startWithSystem: true };
function loadPrefs() { try { Object.assign(prefs, JSON.parse(fs.readFileSync(PREFS_FILE(), 'utf8'))); } catch (e) { /* first run */ } }
function savePrefs() { try { fs.writeFileSync(PREFS_FILE(), JSON.stringify(prefs, null, 1)); } catch (e) { log.warn('prefs', e.message); } }
let pinned = true;
let updateState = { status: 'idle' };

// one Galley at a time: a second launch just shows the first one
if (!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance', () => showWindow());

// ---------------------------------------------------------------- engine
function ping() {
  return new Promise((resolve) => {
    const req = http.get(`${URL}/api/c/state`, { timeout: 1500 }, (res) => { res.resume(); resolve(res.statusCode === 200); });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function engineCommand() {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'galley-engine.exe' : 'galley-engine';
    return { cmd: path.join(process.resourcesPath, 'engine', exe), args: ['--no-browser'] };
  }
  // development: run the Python server from the project folder
  return { cmd: process.platform === 'win32' ? 'python' : 'python3', args: [path.join(__dirname, '..', 'ui', 'server.py'), '--no-browser'] };
}

async function startEngine() {
  if (await ping()) { log.info('engine already running, reusing it'); return true; }
  const { cmd, args } = engineCommand();
  log.info('starting engine', cmd);
  engine = spawn(cmd, args, {
    env: { ...process.env, GALLEY_PORT: String(PORT), GALLEY_VERSION: app.getVersion() },
    windowsHide: true, stdio: 'ignore',
  });
  engine.on('exit', (code) => { log.warn('engine exited', code); engine = null; });
  for (let i = 0; i < 120; i++) {           // up to 30 s on a slow first start
    if (await ping()) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

function stopEngine() { if (engine) { try { engine.kill(); } catch (e) { /* already gone */ } engine = null; } }

// ---------------------------------------------------------------- window
function dock() {
  const wa = screen.getPrimaryDisplay().workArea;
  win.setBounds({ x: wa.x + wa.width - WIDTH, y: wa.y, width: WIDTH, height: wa.height });
}

function createWindow() {
  win = new BrowserWindow({
    width: WIDTH, height: 800, minWidth: 360, title: 'Galley Copilot', show: false, autoHideMenuBar: true,
    alwaysOnTop: pinned, icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  win.setAlwaysOnTop(pinned, 'floating');
  dock();
  win.loadFile(path.join(__dirname, 'splash.html'));
  // started by the computer at login: stay in the tray until InDesign opens
  win.once('ready-to-show', () => { if (!process.argv.includes('--hidden')) win.show(); });
  // links (Pinterest boards, PDFs) open in the normal browser, not inside the copilot
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.on('close', (e) => { if (!quitting) { e.preventDefault(); win.hide(); userHid = true; } });   // close = hide to tray
}

function showWindow() { if (!win) return; userHid = false; if (win.isMinimized()) win.restore(); win.show(); win.focus(); }

function setPinned(v) {
  pinned = prefs.pinned = v; savePrefs(); if (win) win.setAlwaysOnTop(v, 'floating');
  buildTray();
}

// ---------------------------------------------------------------- like a plugin: start with the computer, appear with InDesign
function applyLoginItem() {
  if (!app.isPackaged) return;  // only the installed app registers itself
  app.setLoginItemSettings({ openAtLogin: prefs.startWithSystem, args: ['--hidden'] });
}

function isInDesignRunning() {
  return new Promise((resolve) => {
    const cmd = process.platform === 'win32' ? 'tasklist /FI "IMAGENAME eq InDesign.exe" /NH' : 'pgrep -f "Adobe InDesign"';
    require('child_process').exec(cmd, { windowsHide: true, timeout: 5000 }, (err, out) => {
      resolve(process.platform === 'win32' ? /InDesign\.exe/i.test(out || '') : !err && !!(out || '').trim());
    });
  });
}

async function watchInDesign() {
  const now = await isInDesignRunning();
  if (now !== indesignOpen) {
    indesignOpen = now;
    log.info('InDesign', now ? 'opened' : 'closed');
    if (prefs.followInDesign && win) {
      if (now && !userHid) { dock(); win.showInactive(); }    // appear beside InDesign without stealing focus
      if (!now) { win.hide(); userHid = false; }
    }
  }
}

// ---------------------------------------------------------------- tray
function dataFolder() {
  const base = process.platform === 'win32' ? path.join(process.env.APPDATA || app.getPath('appData'), 'Galley')
    : process.platform === 'darwin' ? path.join(app.getPath('home'), 'Library', 'Application Support', 'Galley') : path.join(app.getPath('home'), '.galley');
  fs.mkdirSync(base, { recursive: true });
  return base;
}

function buildTray() {
  if (!tray) {
    tray = new Tray(nativeImage.createFromPath(path.join(__dirname, 'assets', 'tray.png')));
    tray.setToolTip('Galley');
    tray.on('click', showWindow);
  }
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show Galley', click: showWindow },
    { label: 'Dock to the right', click: () => { dock(); showWindow(); } },
    { label: 'Keep on top of InDesign', type: 'checkbox', checked: pinned, click: (m) => setPinned(m.checked) },
    { label: 'Show when InDesign opens', type: 'checkbox', checked: prefs.followInDesign, click: (m) => { prefs.followInDesign = m.checked; savePrefs(); } },
    { label: 'Start Galley with my computer', type: 'checkbox', checked: prefs.startWithSystem, visible: app.isPackaged,
      click: (m) => { prefs.startWithSystem = m.checked; savePrefs(); applyLoginItem(); } },
    { type: 'separator' },
    { label: 'Check for updates', click: () => checkUpdates(true) },
    { label: 'Open my Galley folder', click: () => shell.openPath(dataFolder()) },
    { label: `Version ${app.getVersion()}`, enabled: false },
    { type: 'separator' },
    { label: 'Quit Galley', click: () => { quitting = true; app.quit(); } },
  ]));
}

// ---------------------------------------------------------------- updates
function sendUpdate(state) {
  updateState = state;
  if (win) win.webContents.send('galley:update', state);
}

function checkUpdates(manual) {
  if (!app.isPackaged) { if (manual) dialog.showMessageBox({ message: 'Updates work in the installed app, not in development.' }); return; }
  autoUpdater.checkForUpdates().catch((e) => { log.warn('update check failed', e.message); if (manual) sendUpdate({ status: 'error', message: e.message }); });
}

function setupUpdates() {
  // GALLEY_UPDATE_URL points at any folder of release files (for testing, or a company server);
  // otherwise the publish settings in package.json are used (GitHub Releases)
  if (process.env.GALLEY_UPDATE_URL) autoUpdater.setFeedURL({ provider: 'generic', url: process.env.GALLEY_UPDATE_URL });
  autoUpdater.autoDownload = true;
  autoUpdater.on('checking-for-update', () => sendUpdate({ status: 'checking' }));
  autoUpdater.on('update-available', (i) => sendUpdate({ status: 'downloading', version: i.version }));
  autoUpdater.on('update-not-available', () => sendUpdate({ status: 'current', version: app.getVersion() }));
  autoUpdater.on('download-progress', (p) => sendUpdate({ status: 'downloading', percent: Math.round(p.percent), version: updateState.version }));
  autoUpdater.on('update-downloaded', (i) => {
    sendUpdate({ status: 'ready', version: i.version });
    // test switch: install without waiting for the "Restart to update" click
    if (process.env.GALLEY_AUTO_INSTALL_UPDATE === '1') { log.info('auto-installing', i.version); quitting = true; stopEngine(); autoUpdater.quitAndInstall(true, true); }
  });
  autoUpdater.on('error', (e) => { log.warn('updater', e && e.message); sendUpdate({ status: 'error', message: String(e && e.message || e) }); });
  checkUpdates(false);
  setInterval(() => checkUpdates(false), 4 * 60 * 60 * 1000);
}

ipcMain.handle('galley:info', () => ({ version: app.getVersion(), update: updateState, pinned }));
ipcMain.handle('galley:install-update', () => { quitting = true; stopEngine(); autoUpdater.quitAndInstall(true, true); });
ipcMain.handle('galley:pin', (e, v) => setPinned(!!v));
ipcMain.handle('galley:check-updates', () => checkUpdates(true));

// ---------------------------------------------------------------- start / stop
app.whenReady().then(async () => {
  if (process.platform === 'darwin' && app.dock) app.dock.hide();   // a side panel, not a dock app
  loadPrefs(); pinned = prefs.pinned; applyLoginItem();
  createWindow();
  buildTray();
  const ok = await startEngine();
  if (ok) win.loadURL(`${URL}/copilot`);
  else win.webContents.executeJavaScript(`document.getElementById('msg').textContent = 'Galley could not start its engine. Restart Galley; if it keeps happening, send the log from Help.'`);
  setupUpdates();
  watchInDesign(); setInterval(watchInDesign, 3000);
});

app.on('before-quit', () => { quitting = true; stopEngine(); });
app.on('window-all-closed', (e) => e.preventDefault());   // keep running in the tray
