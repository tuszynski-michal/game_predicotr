import { contextBridge, ipcRenderer } from 'electron';
import { CHANNELS, type SelectorBridge } from './contracts.ts';
const bridge = Object.freeze<SelectorBridge>({
  begin: () => ipcRenderer.invoke(CHANNELS.begin),
  legacyPreview: () => ipcRenderer.invoke(CHANNELS.legacyPreview),
  legacyAdopt: (token) => ipcRenderer.invoke(CHANNELS.legacyAdopt, token),
  openLogs: () => ipcRenderer.invoke(CHANNELS.openLogs),
  create: (options) => ipcRenderer.invoke(CHANNELS.create, options),
  open: () => ipcRenderer.invoke(CHANNELS.open),
  recent: () => ipcRenderer.invoke(CHANNELS.recent),
  continue: (projectId) => ipcRenderer.invoke(CHANNELS.continue, projectId),
  snapshot: () => ipcRenderer.invoke(CHANNELS.snapshot),
  execute: (request) => ipcRenderer.invoke(CHANNELS.execute, request),
  resume: () => ipcRenderer.invoke(CHANNELS.resume),
  relink: (kind) => ipcRenderer.invoke(CHANNELS.relink, kind),
  restartPreview: () => ipcRenderer.invoke(CHANNELS.restartPreview),
  saveView: (projectId, view) =>
    ipcRenderer.invoke(CHANNELS.saveView, projectId, view),
  close: () => ipcRenderer.invoke(CHANNELS.close),
  openOutput: () => ipcRenderer.invoke(CHANNELS.openOutput),
  fullscreen: () => ipcRenderer.invoke(CHANNELS.fullscreen),
});
contextBridge.exposeInMainWorld('selector', bridge);
