import { contextBridge, ipcRenderer } from 'electron';
contextBridge.exposeInMainWorld('navigation', {
  open: address => ipcRenderer.invoke('navigation:open', address)
});
