import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// Local fixture browser only: no app service, operator image or API is used.
const repo = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../..',
);
const output = path.join(repo, 'artifacts', 'grid-shadow-mobile-smoke');
const edge =
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
assert.ok(
  existsSync(edge),
  'The already-installed Edge browser is required. No download is allowed.',
);
await mkdir(output, { recursive: true });
const absolute = (relative) =>
  JSON.stringify(path.join(repo, relative).replaceAll('\\', '/'));
const entry = `
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {GridShadowPanel} from ${absolute('apps/admin/src/features/grid-shadow/grid-shadow-panel.tsx')};
import {BoardGeometryCorrectionEditor} from ${absolute('apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx')};
import ${absolute('apps/admin/src/app/globals.css')};
import ${absolute('apps/reviewer/src/app/reviewer.css')};
const source='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="#3b6189"/><text x="100" y="180" fill="white" font-size="40">Mock 5 x 3</text></svg>');
const corners=[{x:50,y:50},{x:550,y:50},{x:550,y:350},{x:50,y:350}];
const calls={starts:[],previews:[],saves:[]};
const api={listImageGridReviews:async()=>{await new Promise(r=>setTimeout(r,180));return {data:{items:[{sourceImageId:'mock-source',sequenceNumber:1}]}}},listGridShadowResults:async()=>({data:{items:[],nextCursor:null}}),startGridShadowJob:async command=>{calls.starts.push(command);return {error:{code:'GRID_SHADOW_DISABLED',message:'disabled'}}},getGridShadowResult:async()=>({data:null}),imageGridReviewSourceAssetUrl:()=>source,startLocalReviewer:async()=>({data:null}),getJob:async()=>({data:null})};
const target={key:'mobile-mock',load:async()=>({ok:true,view:{initialFlags:{partial:false,exclude:false,includeInPartialGridTraining:false,manualUnavailable:[]},kind:'reported',metadata:[{label:'Numer planszy',value:'1'}],reportedCellIndices:[],saveHint:'Mock: zapis wyłącznie do pamięci testu.',sourceHeight:400,sourceWidth:600,sourceUrl:source,suggestedCorners:corners,supportsPartial:true}}),commandKey:(corners,flags)=>JSON.stringify({corners,flags}),preview:async(corners,flags)=>{calls.previews.push({corners,flags});const canvas=document.createElement('canvas');canvas.width=480;canvas.height=288;const ctx=canvas.getContext('2d');ctx.fillStyle='#476c5e';ctx.fillRect(0,0,480,288);return {ok:true,blob:await new Promise(r=>canvas.toBlob(r,'image/png'))}},symbols:async()=>({ok:true,cells:[]}),save:async(...args)=>{calls.saves.push(args);return {ok:true,reviewItemId:'mock'}}};
function App(){const [view,setView]=useState('panel');window.mobileSmoke={calls,showEditor:()=>setView('editor')};return <main className={view==='editor'?'reviewerShell':''} style={{padding:12,maxWidth:1000,margin:'0 auto'}}>{view==='panel'?<GridShadowPanel api={api} gameId="mock-game"/>:<BoardGeometryCorrectionEditor target={target} symbols={[{id:'cherry',label:'Wiśnia',shortcut:'1'},{id:'plum',label:'Śliwka',shortcut:'5'}]} autoSelectFirstCell previewWhileSourceLoads unknownSymbolShortcut="9" onSaved={async()=>{}} onConflict={async()=>{}}/>}</main>}
createRoot(document.getElementById('root')).render(<App/>);
window.touchTrace=[];for(const type of ['pointerdown','touchstart','touchend','click'])document.addEventListener(type,event=>window.touchTrace.push({type,target:event.target.getAttribute?.('aria-label')??event.target.textContent,scrollY,visual:visualViewport?{offsetTop:visualViewport.offsetTop,offsetLeft:visualViewport.offsetLeft,scale:visualViewport.scale}:null}),true);
`;
await build({
  stdin: {
    contents: entry,
    resolveDir: repo,
    sourcefile: 'mobile-fixture.tsx',
    loader: 'tsx',
  },
  bundle: true,
  jsx: 'automatic',
  alias: {
    react: path.join(repo, 'node_modules/react'),
    'react-dom': path.join(repo, 'node_modules/react-dom'),
  },
  format: 'iife',
  platform: 'browser',
  outfile: path.join(output, 'fixture.js'),
  tsconfig: path.join(repo, 'apps/admin/tsconfig.json'),
  plugins: [
    {
      name: 'css-modules',
      setup(build) {
        build.onLoad({ filter: /\.module\.css$/ }, async ({ path }) => ({
          contents: await readFile(path, 'utf8'),
          loader: 'local-css',
        }));
      },
    },
  ],
  logLevel: 'silent',
});
const html =
  '<!doctype html><html lang="pl"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"><div id="root"></div><script src="/fixture.js"></script></html>';
await writeFile(path.join(output, 'index.html'), html);
const server = http.createServer(async (request, response) => {
  const name = request.url === '/' ? 'index.html' : request.url?.slice(1);
  if (!['index.html', 'fixture.js', 'fixture.css'].includes(name)) {
    response.writeHead(404);
    response.end();
    return;
  }
  try {
    response.setHeader(
      'Content-Type',
      name.endsWith('.js')
        ? 'text/javascript'
        : name.endsWith('.css')
          ? 'text/css'
          : 'text/html',
    );
    response.end(await readFile(path.join(output, name)));
  } catch {
    response.writeHead(500);
    response.end();
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = path.join(output, `edge-profile-${process.pid}`);
const child = spawn(
  edge,
  [
    '--headless=new',
    '--no-first-run',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-sync',
    '--disable-extensions',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    'about:blank',
  ],
  { windowsHide: true, stdio: 'ignore' },
);
await writeFile(
  path.join(output, 'process.json'),
  JSON.stringify(
    { nodePid: process.pid, edgePid: child.pid, origin, profile },
    null,
    2,
  ),
);
let ws;
const commands = new Map();
let id = 0;
const errors = [];
const stopBrowser = () => {
  const literalProfile = profile.replaceAll("'", "''");
  spawnSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-Command',
      `Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('${literalProfile}') -and $_.CommandLine.Contains('--headless') } | ForEach-Object { & taskkill.exe /PID $_.ProcessId /T /F }`,
    ],
    { timeout: 10000, windowsHide: true, stdio: 'ignore' },
  );
  if (child.exitCode === null)
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      timeout: 10000,
      windowsHide: true,
      stdio: 'ignore',
    });
};
const deadline = setTimeout(() => {
  stopBrowser();
  server.close();
}, 90000);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function poll(read, accept, description) {
  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      const value = await read();
      if (accept(value)) return value;
    } catch {
      /* browser boot or fixture render still pending */
    }
    await delay(100);
  }
  throw new Error(`Timeout: ${description}`);
}
function cdp(method, params = {}) {
  const next = ++id;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      commands.delete(next);
      reject(new Error(`CDP timeout: ${method}`));
    }, 5000);
    commands.set(next, {
      resolve: (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      reject: (value) => {
        clearTimeout(timeout);
        reject(value);
      },
    });
    ws.send(JSON.stringify({ id: next, method, params }));
  });
}
async function evaluate(expression) {
  const result = await cdp('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails)
    throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
async function tap(selector) {
  const point = await evaluate(
    `(async()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing touch target');e.scrollIntoView({block:'center',behavior:'instant'});await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()`,
  );
  await cdp('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [point],
  });
  await delay(60);
  await cdp('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
}
const report = {
  browser: 'Installed Microsoft Edge, Chromium mobile emulation',
  physicalAndroid: false,
  operatorData: false,
  viewports: [],
  errors,
};
try {
  const active = await poll(
    () => readFile(path.join(profile, 'DevToolsActivePort'), 'utf8'),
    (value) => value.includes('\n'),
    'Edge DevTools startup',
  );
  const port = Number(active.split('\n')[0]);
  const pages = await poll(
    async () =>
      (
        await fetch(`http://127.0.0.1:${port}/json/list`, {
          signal: AbortSignal.timeout(2000),
        })
      ).json(),
    (value) => value.some((target) => target.type === 'page'),
    'Edge page',
  );
  ws = new WebSocket(
    pages.find((target) => target.type === 'page').webSocketDebuggerUrl,
  );
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
  ws.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && commands.has(message.id)) {
      const command = commands.get(message.id);
      commands.delete(message.id);
      if (message.error)
        command.reject(new Error(JSON.stringify(message.error)));
      else command.resolve(message.result);
    }
    if (message.method === 'Runtime.exceptionThrown')
      errors.push(message.params);
  });
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  for (const width of [390, 360]) {
    await cdp('Emulation.setDeviceMetricsOverride', {
      width,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await cdp('Emulation.setTouchEmulationEnabled', {
      enabled: true,
      maxTouchPoints: 1,
    });
    await cdp('Page.navigate', { url: origin });
    await poll(
      () => evaluate(`document.querySelector('label input')!==null`),
      Boolean,
      'panel sources',
    );
    const panel = await evaluate(
      `({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,choiceHeight:document.querySelector('label').getBoundingClientRect().height,buttonHeights:[...document.querySelectorAll('[aria-label="Porównanie siatek sieci"] button')].map(e=>e.getBoundingClientRect().height),emptyHistory:document.body.textContent.includes('Nie ma jeszcze wyników porównań'),touchPoints:navigator.maxTouchPoints})`,
    );
    assert.ok(
      panel.scrollWidth <= panel.width + 1,
      `Panel horizontal overflow at ${width}`,
    );
    assert.ok(panel.choiceHeight >= 48);
    assert.ok(panel.buttonHeights.every((height) => height >= 44));
    assert.ok(panel.emptyHistory);
    assert.equal(panel.touchPoints, 1);
    await tap('label');
    assert.equal(
      await evaluate(`document.querySelector('label input').checked`),
      true,
    );
    await tap('[aria-label="Porównanie siatek sieci"] button.primaryButton');
    await poll(
      () =>
        evaluate(
          `document.body.textContent.includes('Tryb porównawczy jest wyłączony')`,
        ),
      Boolean,
      'mock start refusal',
    );
    assert.equal(await evaluate('window.mobileSmoke.calls.starts.length'), 1);
    await evaluate('window.scrollTo(0,0)');
    const panelScreen = await cdp('Page.captureScreenshot', { format: 'png' });
    await writeFile(
      path.join(output, `panel-${width}.png`),
      Buffer.from(panelScreen.data, 'base64'),
    );
    await evaluate('window.mobileSmoke.showEditor()');
    await poll(
      () =>
        evaluate(
          `document.querySelector('button[aria-label^="Crop 1"]')?.getAttribute('aria-pressed')==='true' && document.querySelector('canvas')!==null && !document.body.textContent.includes('Wczytywanie obrazu')`,
        ),
      Boolean,
      'editor preview',
    );
    await tap('button[aria-label^="Crop 2"]');
    await poll(
      () =>
        evaluate(
          `document.querySelector('button[aria-label^="Crop 2"]')?.getAttribute('aria-pressed')==='true'`,
        ),
      Boolean,
      'editor touched cell selection',
    );
    const symbolSelector =
      '[aria-label="Symbol wybranego pola"] button[aria-keyshortcuts="1"]';
    await tap(symbolSelector);
    await poll(
      () =>
        evaluate(
          `document.querySelector('button[aria-label^="Crop 2"]')?.getAttribute('aria-label')?.includes('Wiśnia')`,
        ),
      Boolean,
      'editor touched symbol selection',
    );
    const editor = await evaluate(
      `({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,crops:document.querySelectorAll('button[aria-label^="Crop "]').length,previews:window.mobileSmoke.calls.previews.length,saves:window.mobileSmoke.calls.saves.length,canvasTouchAction:getComputedStyle(document.querySelector('canvas')).touchAction})`,
    );
    assert.ok(
      editor.scrollWidth <= editor.width + 1,
      `Editor horizontal overflow at ${width}`,
    );
    assert.equal(editor.crops, 15);
    assert.equal(editor.saves, 0);
    assert.ok(editor.previews >= 1);
    await evaluate(
      'document.querySelector("canvas").scrollIntoView({block:"center"})',
    );
    const editorScreen = await cdp('Page.captureScreenshot', { format: 'png' });
    await writeFile(
      path.join(output, `editor-${width}.png`),
      Buffer.from(editorScreen.data, 'base64'),
    );
    report.viewports.push({
      width,
      height: 844,
      panel,
      editor,
      panelTouchSelection: true,
      editorTouchSymbolSelection: true,
      nativeTouchTrace: await evaluate('window.touchTrace'),
    });
  }
  assert.equal(
    errors.length,
    0,
    'The browser must not raise uncaught exceptions.',
  );
  report.passed = true;
} catch (error) {
  report.failure = String(error);
  if (ws?.readyState === WebSocket.OPEN)
    report.touchTrace = await evaluate('window.touchTrace');
  if (ws?.readyState === WebSocket.OPEN) {
    report.failureState = await evaluate(
      `({text:document.body.textContent,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,selected:[...document.querySelectorAll('button[aria-pressed="true"]')].map(e=>e.getAttribute('aria-label')),target:document.querySelector('button[aria-label^="Crop 2"]')?.getBoundingClientRect().toJSON(),hit:(()=>{const e=document.querySelector('button[aria-label^="Crop 2"]');if(!e)return null;const r=e.getBoundingClientRect();return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.outerHTML})()})`,
    );
    const screenshot = await cdp('Page.captureScreenshot', { format: 'png' });
    await writeFile(
      path.join(output, 'failure.png'),
      Buffer.from(screenshot.data, 'base64'),
    );
  }
  throw error;
} finally {
  clearTimeout(deadline);
  ws?.close();
  stopBrowser();
  await new Promise((resolve) => server.close(resolve));
  await writeFile(
    path.join(output, 'report.json'),
    JSON.stringify(report, null, 2),
  );
}
console.log(JSON.stringify(report, null, 2));
