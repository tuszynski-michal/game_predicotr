import { contextBridge, ipcRenderer } from 'electron';
import { CHANNELS, type SelectorBridge } from './contracts.ts';
const bridge: SelectorBridge = Object.freeze({
  pickSource: () => ipcRenderer.invoke(CHANNELS.pickSource),
  openLogs: () => ipcRenderer.invoke(CHANNELS.openLogs),
});
contextBridge.exposeInMainWorld('selector', bridge);
