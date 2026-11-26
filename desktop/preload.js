// The small, safe bridge between the copilot page and the desktop app (no Node access for the page itself).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('galleyApp', {
  info: () => ipcRenderer.invoke('galley:info'),
  onUpdate: (cb) => ipcRenderer.on('galley:update', (_e, state) => cb(state)),
  installUpdate: () => ipcRenderer.invoke('galley:install-update'),
  checkUpdates: () => ipcRenderer.invoke('galley:check-updates'),
  setPinned: (v) => ipcRenderer.invoke('galley:pin', v),
});
