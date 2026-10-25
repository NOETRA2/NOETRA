// Synthetic fixture owned by this project. Static analysis only; Electron is not installed.
import { app, BrowserWindow, ipcMain } from 'electron';
import { fileURLToPath } from 'node:url';
let window;
app.whenReady().then(() => {
  window = new BrowserWindow({ webPreferences: {
    sandbox: true, contextIsolation: true, nodeIntegration: false,
    preload: fileURLToPath(new URL('./preload.js', import.meta.url))
  } });
  window.loadFile('index.html');
});
// Deliberate defect for investigation: preload invokes a different literal IPC channel.
ipcMain.handle('navigation:go', async (_event, address) => {
  const url = new URL(address);
  if (url.protocol !== 'https:') throw new Error('HTTPS required');
  return window.loadURL(url.href);
});
