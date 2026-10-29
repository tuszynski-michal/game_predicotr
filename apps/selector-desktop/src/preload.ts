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
  games: () => ipcRenderer.invoke(CHANNELS.games),
  addGame: (name) => ipcRenderer.invoke(CHANNELS.addGame, name),
  continue: (projectId) => ipcRenderer.invoke(CHANNELS.continue, projectId),
  snapshot: () => ipcRenderer.invoke(CHANNELS.snapshot),
  execute: (request) => ipcRenderer.invoke(CHANNELS.execute, request),
  resume: () => ipcRenderer.invoke(CHANNELS.resume),
  relink: (kind) => ipcRenderer.invoke(CHANNELS.relink, kind),
  restartPreview: () => ipcRenderer.invoke(CHANNELS.restartPreview),
  saveView: (projectId, view) =>
    ipcRenderer.invoke(CHANNELS.saveView, projectId, view),
  close: () => ipcRenderer.invoke(CHANNELS.close),
  shutdownReady: (reply) => ipcRenderer.invoke(CHANNELS.shutdownReady, reply),
  onShutdownRequested: (listener) => {
    const receive = (_event: Electron.IpcRendererEvent, request: unknown) => {
      if (
        request &&
        typeof request === 'object' &&
        'token' in request &&
        typeof request.token === 'string' &&
        'projectId' in request &&
        (request.projectId === null || typeof request.projectId === 'string')
      )
        listener(request as import('./contracts.ts').ShutdownRequest);
    };
    ipcRenderer.on(CHANNELS.shutdownRequested, receive);
    return () =>
      ipcRenderer.removeListener(CHANNELS.shutdownRequested, receive);
  },
  onShutdownCancelled: (listener) => {
    const receive = (_event: Electron.IpcRendererEvent, message: unknown) => {
      if (typeof message === 'string') listener(message);
    };
    ipcRenderer.on(CHANNELS.shutdownCancelled, receive);
    return () =>
      ipcRenderer.removeListener(CHANNELS.shutdownCancelled, receive);
  },
  openOutput: () => ipcRenderer.invoke(CHANNELS.openOutput),
  fullscreen: () => ipcRenderer.invoke(CHANNELS.fullscreen),
  onFullscreenChanged: (listener) => {
    const receive = (_event: Electron.IpcRendererEvent, active: unknown) => {
      if (typeof active === 'boolean') listener(active);
    };
    ipcRenderer.on(CHANNELS.fullscreenChanged, receive);
    return () =>
      ipcRenderer.removeListener(CHANNELS.fullscreenChanged, receive);
  },
});
contextBridge.exposeInMainWorld('selector', bridge);
