import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// A finite fixture server and new isolated browser profile. No application
// service, operator data, database, credential or restart is used.
const repo = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../..',
);
const output = path.join(repo, 'artifacts', 'board-search-sequence-browser');
await mkdir(output, { recursive: true });
const runtime =
  process.env.PLAYWRIGHT_MODULE ??
  path.join(
    os.homedir(),
    '.cache',
    'codex-runtimes',
    'codex-primary-runtime',
    'dependencies',
    'node',
    'node_modules',
    'playwright',
  );
const { chromium } = createRequire(import.meta.url)(runtime);
const executablePath =
  process.env.BROWSER_EXECUTABLE ??
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(
  existsSync(executablePath),
  'Use an installed browser; never download one.',
);
const absolute = (name) =>
  JSON.stringify(path.join(repo, name).replaceAll('\\', '/'));
const entry = `
import React from 'react';
import {createRoot} from 'react-dom/client';
import {BoardSearchWorkspace} from ${absolute('packages/board-search-ui/src/board-search-workspace.tsx')};
import {createBoardSearchShareDataSource} from ${absolute('apps/reviewer/src/features/board-search-share/board-search-share-data-source.ts')};
import ${absolute('packages/ui/src/theme.css')};
import ${absolute('packages/ui/src/buttons.css')};
import ${absolute('packages/board-search-ui/src/board-search.css')};
const host=new URLSearchParams(location.search).get('host')??'admin';
const scopes={admin:'admin:g',share:'share:s',panel:'panel:p:s'};
const symbols=['A','B'].map((code,index)=>({id:code,code,name:code==='A'?'Wiśnia':'Cytryna',mobileCode:index+1,displayOrder:index,imagePath:null,imageRevision:null,status:'active'}));
const board=(sequenceNumber)=>({assetMode:'operational_review',boardChecksumSha256:'a'.repeat(64),reviewItemId:null,importJobId:null,recognizedBoardId:null,sequenceNumber,status:'pending',score:{score:100,exactMatchCount:1,alternativeMatchCount:0,mismatchCount:0,unknownCount:0}});
const state={fresh:true};
const sequence=(count)=>({gameId:'g',scope:'all_searchable',queryCellCount:count,patternCount:count,superGameState:state,searchContextId:'fixture-context',results:[6,2].map((start)=>({startSequenceNumber:start,endSequenceNumber:((start+count-2)%6)+1,score:{...board(1).score,score:87.5},boards:Array.from({length:count},(_,index)=>board(((start+index-1)%6)+1))}))});
const single=()=>({gameId:'g',scope:'all_searchable',queryCellCount:1,superGameState:state,searchContextId:'fixture-context',results:[board(6),board(2)]});
const range=(request)=>({gameId:'g',dataSource:'operational_review',dataFingerprintSha256:'a'.repeat(64),startSequenceNumber:request.startSequenceNumber,requestedSpinCount:request.spinCount,evaluatedSpinCount:request.spinCount,sequenceLength:6,wrappedAtSequenceEnd:true,startBoardStatus:null,rules:{rulesVersionId:'r',rulesVersion:1,spinCost:0},completeness:{completeBoardCount:0,missingBoardCount:request.spinCount,partialBoardCount:0},rows:[],summary:{balanceCredits:0,recognizedPayoutCredits:0,spinCostCredits:0}});
window.fixtureRequests=[];
window.fixtureResponses=[];
const waitForSearch=()=>new Promise(resolve=>setTimeout(resolve,new URLSearchParams(location.search).has('slowSearch')?100:0));
const fixtureSearch=async(kind,request)=>{
 const receipt={kind,request};window.fixtureRequests.push(receipt);
 await waitForSearch();
 const body=kind==='sequence'?sequence(request.patterns.length):single();
 // Distinct scores for limits 7/8/9 prove the new response was rendered;
 // an old enabled button or unchanged heading cannot satisfy the wait.
 for(const result of body.results)result.score.score=request.limit??100;
 window.fixtureResponses.push(receipt);return body;
};
const api={listSymbols:async()=>({data:symbols}),symbolImageAssetUrl:()=>'/view.svg',boardSearchBoardViewUrl:()=>'/view.svg',searchGameBoards:async(_id,request)=>({data:await fixtureSearch('single',request)}),searchGameBoardSequence:async(_id,request)=>({data:await fixtureSearch('sequence',request)}),getBoardSearchApproximateWin:async(_id,request)=>({data:range(request)}),getBoardSearchBoardDetail:async()=>({error:{code:'FIXTURE',message:'Fixture'}})};
const share=host==='admin'?null:createBoardSearchShareDataSource({sessionId:'s',apiBase:host==='panel'?'/fixture/panel':'/fixture/share',fetchImplementation:async(url,options={})=>{
 const parsed=new URL(url,location.href);let body;
 if(parsed.pathname.endsWith('/symbols'))body=symbols;
 else if(parsed.pathname.endsWith('/search')){const request=options.method==='POST'?JSON.parse(options.body):{};body=await fixtureSearch(options.method==='POST'?'sequence':'single',request);}
 else if(parsed.pathname.endsWith('/approximate-win'))body=range({startSequenceNumber:Number(parsed.searchParams.get('startSequenceNumber')),spinCount:Number(parsed.searchParams.get('spinCount'))});
 else throw new Error('Unexpected fixture route '+url);
 return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
}});
const client=share===null?api:{...share,boardSearchBoardViewUrl:()=>'/view.svg'};
createRoot(document.getElementById('root')).render(<React.StrictMode><main className="fixtureShell"><BoardSearchWorkspace client={client} gameId={host==='admin'?'g':'shared'} scopeKey={scopes[host]}/></main></React.StrictMode>);
`;
await build({
  stdin: {
    contents: entry,
    resolveDir: repo,
    sourcefile: 'sequence-fixture.tsx',
    loader: 'tsx',
  },
  bundle: true,
  format: 'iife',
  outfile: path.join(output, 'bundle.js'),
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' },
  logLevel: 'warning',
});
const html =
  '<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/bundle.css"><style>*{box-sizing:border-box}body{margin:0;background:var(--background);color:var(--text);font:15px system-ui}.fixtureShell{max-width:1280px;margin:auto;padding:20px}button,input,select{font:inherit}button{cursor:pointer}button:disabled{cursor:default;opacity:.55}</style><div id="root"></div><script src="/bundle.js"></script></html>';
const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="360"><rect width="600" height="360" fill="#132238"/><g fill="#70e1b4" stroke="#07101d" stroke-width="5">' +
  Array.from(
    { length: 15 },
    (_, index) =>
      `<rect x="${(index % 5) * 120}" y="${Math.floor(index / 5) * 120}" width="120" height="120" rx="15"/>`,
  ).join('') +
  '<text x="300" y="190" text-anchor="middle" fill="#07101d" stroke="none" font-size="40">Plansza testowa</text></g></svg>';
const server = http.createServer(async (req, res) => {
  try {
    const name = new URL(req.url, 'http://fixture').pathname;
    if (name === '/bundle.js' || name === '/bundle.css') {
      res.setHeader(
        'Content-Type',
        name.endsWith('.js') ? 'text/javascript' : 'text/css',
      );
      res.end(await readFile(path.join(output, name.slice(1))));
    } else if (name === '/view.svg') {
      res.setHeader('Content-Type', 'image/svg+xml');
      res.end(svg);
    } else {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end(html);
    }
  } catch {
    res.statusCode = 500;
    res.end('Fixture error');
  }
});
await new Promise((resolve, reject) => {
  const timer = setTimeout(
    () => reject(new Error('Fixture readiness timeout')),
    10000,
  );
  server.once('error', reject);
  server.listen(0, '127.0.0.1', () => {
    clearTimeout(timer);
    resolve();
  });
});
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = path.join(output, `profile-${Date.now()}`);
let context;
const failures = [];
const checks = [];
const launch = async () => {
  const context = await chromium.launchPersistentContext(profile, {
    executablePath,
    headless: true,
    viewport: { width: 1280, height: 900 },
    timeout: 15000,
  });
  context.on('page', (page) =>
    page.on('pageerror', (error) => failures.push(error.message)),
  );
  return context;
};
const click = async (page, text) =>
  page
    .getByRole('button', { name: text, exact: true })
    .click({ timeout: 10000 });
const palette = async (page, name) =>
  page
    .locator('.boardSearchPalette')
    .getByRole('button', { name, exact: false })
    .click();
const search = async (page) => {
  await click(page, 'Szukaj plansz');
  await page.locator('.boardSearchResults').waitFor();
  await page
    .getByRole('button', { name: 'Szukaj plansz', exact: true })
    .waitFor();
};
async function compose(page, count) {
  await palette(page, 'Wiśnia');
  await search(page);
  for (let index = 1; index < count; index++) {
    await click(page, 'Następny układ');
    await palette(page, index % 2 ? 'Cytryna' : 'Wiśnia');
    await search(page);
  }
}

async function waitForSearchResponse(page, responsesBefore, expected) {
  await page.waitForFunction(
    (before) => window.fixtureResponses.length > before,
    responsesBefore,
  );
  await page
    .locator('.boardSearchResultMetrics')
    .getByText(`${expected.request.limit.toFixed(1)}%`, { exact: true })
    .waitFor();
  await page.waitForFunction(() =>
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent === 'Szukaj plansz' && !button.disabled,
    ),
  );
  assert.deepEqual(
    await page.evaluate(
      (before) => window.fixtureResponses.slice(before),
      responsesBefore,
    ),
    [expected],
    'exactly one completed response with the current query',
  );
}

async function limitClickRegression(page, host, count, slowSearch = true) {
  await page.goto(
    `${origin}/?host=${host}${slowSearch ? '&slowSearch=1' : ''}`,
  );
  const timing = slowSearch ? 'delayed' : 'immediate';
  await compose(page, count);
  await page.getByRole('heading', { name: /^Plansza startowa #/ }).waitFor();
  await palette(page, 'Cytryna');
  const expected = await page.evaluate(() => {
    const previous = window.fixtureRequests.at(-1);
    const request = structuredClone(previous.request);
    const cells =
      previous.kind === 'single'
        ? request.cells
        : request.patterns.at(-1).cells;
    cells.push({ cellIndex: 5, symbolCode: 'B' });
    request.limit = 7;
    return { kind: previous.kind, request };
  });
  const before = await page.evaluate(() => window.fixtureRequests.length);
  const responsesBefore = await page.evaluate(
    () => window.fixtureResponses.length,
  );
  const limit = page.getByRole('spinbutton', {
    name: 'Liczba wyników wyszukiwania',
  });
  await limit.fill('7');
  // A real browser click performs pointerdown -> focusout/blur -> pointerup
  // -> click. Dispatching click alone cannot reproduce P2-4.
  await click(page, 'Szukaj plansz');
  await page.waitForFunction(
    (before) => window.fixtureRequests.length > before,
    before,
  );
  const sent = await page.evaluate(
    (before) => window.fixtureRequests.slice(before),
    before,
  );
  assert.deepEqual(
    sent,
    [expected],
    `${host}: first click sends only the current draft with the new limit`,
  );
  checks.push(
    `${host} (${timing}): P2-4 real blur/click sends the edited pattern exactly once`,
  );

  await waitForSearchResponse(page, responsesBefore, expected);
  await page.getByRole('heading', { name: /^Plansza startowa #/ }).waitFor();
  assert.deepEqual(
    await page.evaluate(
      (before) => window.fixtureRequests.slice(before),
      before,
    ),
    [expected],
    `${host}: no additional request after the edited search settles`,
  );
  await click(page, 'Następna →');
  const end = count === 1 ? 2 : 3;
  await page
    .getByRole('heading', {
      name: new RegExp('^Plansza startowa #' + end + ' ·'),
    })
    .waitFor();
  for (const [method, nextLimit] of [
    ['Enter', 8],
    ['click', 9],
  ]) {
    const cleanBefore = await page.evaluate(
      () => window.fixtureRequests.length,
    );
    const cleanResponsesBefore = await page.evaluate(
      () => window.fixtureResponses.length,
    );
    await limit.fill(String(nextLimit));
    if (method === 'Enter') await limit.press('Enter');
    else await click(page, 'Szukaj plansz');
    await page.waitForFunction(
      (before) => window.fixtureRequests.length > before,
      cleanBefore,
    );
    const cleanExpected = [
      { ...expected, request: { ...expected.request, limit: nextLimit } },
    ];
    assert.deepEqual(
      await page.evaluate(
        (before) => window.fixtureRequests.slice(before),
        cleanBefore,
      ),
      cleanExpected,
      `${host}: clean pattern ${method} sends one equivalent request`,
    );
    await waitForSearchResponse(page, cleanResponsesBefore, cleanExpected[0]);
    await page
      .getByRole('heading', {
        name: new RegExp('^Plansza startowa #' + end + ' ·'),
      })
      .waitFor();
    assert.deepEqual(
      await page.evaluate(
        (before) => window.fixtureRequests.slice(before),
        cleanBefore,
      ),
      cleanExpected,
      `${host}: no additional request after clean ${method} settles`,
    );
    assert.match(
      await page.locator('.boardSearchResultMetrics').textContent(),
      count === 1 ? /#2/ : /#2 → #3/,
    );
    checks.push(
      `${host} (${timing}): clean ${method} refresh sends exactly once and preserves selection`,
    );
  }
  await click(page, 'Nowe szukanie');
}
try {
  context = await launch();
  let page = context.pages()[0];
  page.on('pageerror', (error) => failures.push(error.message));
  for (const [host, count] of [
    ['admin', 1],
    ['share', 2],
    ['panel', 2],
  ]) {
    await limitClickRegression(page, host, count);
  }
  await limitClickRegression(page, 'admin', 1, false);
  await page.goto(`${origin}/?host=admin`);
  await compose(page, 4);
  await click(page, 'Następna →');
  await click(page, 'Układ 1');
  await palette(page, 'Cytryna');
  await page.screenshot({
    path: path.join(output, 'desktop.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(output, 'mobile-admin.png'),
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
    'no horizontal overflow at 390px',
  );
  const record = await page.evaluate(() =>
    JSON.parse(localStorage.getItem('board-search-sequence:v1:admin:g')),
  );
  assert.equal(record.patterns.length, 4);
  assert.equal(record.selectedStartSequenceNumber, 2);
  assert.equal(record.lastSubmitted.patterns.length, 4);
  assert.doesNotMatch(
    JSON.stringify(record),
    /context|Checksum|results|credential/,
  );
  checks.push(
    'Admin: four patterns, selected result, dirty draft, desktop/mobile layout',
  );
  for (const host of ['share', 'panel']) {
    await page.goto(`${origin}/?host=${host}`);
    assert.equal(
      await page.getByRole('button', { name: 'Układ 2', exact: true }).count(),
      0,
    );
    await compose(page, 2);
    await page.screenshot({
      path: path.join(output, `mobile-${host}.png`),
      fullPage: true,
    });
    checks.push(`${host}: isolated set and real public adapter POST`);
  }
  await context.close();
  context = await launch();
  page = context.pages()[0];
  page.on('pageerror', (error) => failures.push(error.message));
  for (const [host, count] of [
    ['admin', 4],
    ['share', 2],
    ['panel', 2],
  ]) {
    await page.goto(`${origin}/?host=${host}`);
    await page.locator('.boardSearchResults').waitFor();
    const request = await page.evaluate(() =>
      window.fixtureRequests.find((request) => request.kind === 'sequence'),
    );
    assert.equal(
      request.request.patterns.length,
      count,
      `${host} restored last submission after new process`,
    );
    if (host === 'admin') {
      assert.match(
        await page.locator('.boardSearchResultMetrics').textContent(),
        /#2 → #5/,
      );
      assert.equal(
        await page
          .getByRole('button', { name: 'Układ 1', exact: true })
          .getAttribute('aria-pressed'),
        'true',
      );
      assert.match(await page.locator('body').textContent(), /Wzór zmieniony/);
    }
    checks.push(
      `${host}: local state and selected identity restored in a new browser process`,
    );
  }
  assert.deepEqual(failures, []);
  await writeFile(
    path.join(output, 'verification.json'),
    JSON.stringify({ checks, failures, physicalAndroid: false }, null, 2),
  );
  console.log(JSON.stringify({ checks, failures, artifacts: output }, null, 2));
} finally {
  if (context) await context.close();
  await new Promise((resolve) => server.close(resolve));
}
