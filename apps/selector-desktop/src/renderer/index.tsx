import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.tsx';
import type { SelectorBridge } from '../contracts.ts';
import './style.css';
declare global {
  interface Window {
    selector: SelectorBridge;
  }
}
createRoot(document.getElementById('root')!).render(<App />);
