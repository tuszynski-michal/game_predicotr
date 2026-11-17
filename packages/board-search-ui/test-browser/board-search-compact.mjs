import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// Finite, routed in-memory fixture. No API/Admin service, database or network.
const repo = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../..',
);
const output = path.join(repo, 'artifacts', 'task-1238-verification');
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
const absolute = (file) =>
  JSON.stringify(path.join(repo, file).replaceAll('\\', '/'));
const bundle = await build({
  stdin: {
    resolveDir: repo,
    sourcefile: 'compact-search-fixture.tsx',
    loader: 'tsx',
    contents: `
import React from 'react';
import {createRoot} from 'react-dom/client';
import {BoardSearchWorkspace} from ${absolute('packages/board-search-ui/src/board-search-workspace.tsx')};
const svg=(label,color)=>'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="180"><rect width="300" height="180" fill="'+color+'"/><text x="150" y="100" text-anchor="middle" fill="white" font-family="sans-serif" font-size="30">'+label+'</text></svg>');
const symbols=Array.from({length:10},(_,i)=>({id:String(i),code:'S'+i,name:'Symbol '+i,status:'active',displayOrder:i,mobileCode:i+1,imagePath:'fixture',imageRevision:null}));
const board=(number,score=100)=>({assetMode:'operational_review',sequenceNumber:number,boardChecksumSha256:'a'.repeat(64),reviewItemId:null,importJobId:null,recognizedBoardId:null,status:'accepted',score:{score,exactMatchCount:1,alternativeMatchCount:0,mismatchCount:0,unknownCount:0}});
window.requests=[];
const api={
 listSymbols:async()=>({data:symbols}),
 symbolImageAssetUrl:(_game,id)=>svg('S'+id,['#714a92','#3c6b95','#38694e'][Number(id)%3]),
 boardSearchBoardViewUrl:(_game,number)=>svg('Układ #'+number,'#234964'),
 searchGameBoards:async(_game,request)=>{window.requests.push(request);await new Promise(r=>setTimeout(r,80));return {data:{gameId:'g',scope:'all_searchable',queryCellCount:request.cells.length,results:[board(123),board(78,90)]},searchContextId:'fixture'};},
 getBoardSearchApproximateWin:async(_game,request)=>({data:{gameId:'g',dataSource:'operational_review',dataFingerprintSha256:'b'.repeat(64),startSequenceNumber:request.startSequenceNumber,requestedSpinCount:request.spinCount,evaluatedSpinCount:request.spinCount,sequenceLength:10000,wrappedAtSequenceEnd:false,startBoardStatus:null,rules:{rulesVersionId:'r',rulesVersion:1,spinCost:10},completeness:{completeBoardCount:2500,missingBoardCount:0,partialBoardCount:0},rows:[{spinNumber:200,sequenceNumber:request.startSequenceNumber+200,boardStatus:'accepted',payoutCredits:5000,payoutKind:'exact',cumulativePayoutCredits:5000,cumulativeBalanceCredits:3000}],summary:{balanceCredits:5000-request.spinCount*10,recognizedPayoutCredits:5000,spinCostCredits:request.spinCount*10}}}),
 getBoardSearchBoardDetail:async(_game,number)=>({data:{gameId:'g',sequenceNumber:number,boardChecksumSha256:'a'.repeat(64),documentStale:false,view:{revision:'r'}}}),
};
createRoot(document.getElementById('root')).render(<React.StrictMode><main className="boardSearchShareApp"><header className="boardSearchShareHeader"><label className="boardSearchPanelGame"><select aria-label="Gra" defaultValue="g"><option value="g">Gra testowa</option></select></label></header><BoardSearchWorkspace client={api} gameId="g"/></main></React.StrictMode>);
`,
  },
  bundle: true,
  write: false,
  format: 'iife',
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' },
  logLevel: 'warning',
});
const css = (
  await Promise.all(
    [
      'packages/ui/src/theme.css',
      'packages/ui/src/buttons.css',
      'apps/reviewer/src/app/reviewer.css',
      'packages/board-search-ui/src/board-search.css',
    ].map((file) => readFile(path.join(repo, file), 'utf8')),
  )
).join('\n');
const html = `<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${css}</style><div id="root"></div><script>${bundle.outputFiles[0].text}</script></html>`;
const browser = await chromium.launch({
  executablePath,
  headless: true,
  timeout: 15000,
});
const checks = [];
const failures = [];
try {
  const context = await browser.newContext({ hasTouch: true, isMobile: true });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => failures.push(error.message));
  await page.route('https://board-search-fixture.test/**', (route) =>
    route.fulfill({ contentType: 'text/html; charset=utf-8', body: html }),
  );
  for (const width of [320, 375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('https://board-search-fixture.test/');
    await page.getByTitle('Symbol 0', { exact: true }).tap();
    const search = page.getByRole('button', {
      name: 'Szukaj plansz',
      exact: true,
    });
    await search.tap();
    await page.locator('.boardSearchResultSummary').waitFor();
    assert.equal(
      await page.evaluate(() => window.requests.at(-1).cells.length),
      1,
      'fresh symbol after a restored search starts one new pattern',
    );
    // An identical query may retain the previously selected ranked match.
    const previous = page.getByRole('button', {
      name: '← Poprzednia',
      exact: true,
    });
    if (await previous.isEnabled()) await previous.click();
    assert.match(
      await page.locator('.boardSearchResultSummary').innerText(),
      /Układ #123/,
    );
    assert.equal(
      await page
        .getByRole('button', { name: 'Następny układ', exact: true })
        .count(),
      0,
    );
    assert.equal(await page.locator('.boardSearchEvidence').count(), 0);
    const dimensions = await page.evaluate(() => {
      const bounds = (node) => {
        const rect = node.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      };
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewport: innerWidth,
        tiles: [
          ...document.querySelectorAll(
            '.boardSearchSymbolButton:not([hidden])',
          ),
        ].map(bounds),
        buttons: [
          ...document.querySelectorAll('.boardSearchSubmitActions button'),
        ].map(bounds),
        winControls: [
          ...document.querySelectorAll(
            '.boardSearchApproximateWinControls label',
          ),
        ].map(bounds),
        entryOrder: [
          ...document.querySelectorAll('.boardSearchEntryOrder > label'),
        ].map(bounds),
        resultLimit: bounds(
          document.querySelector(
            '.boardSearchEntryOrder .boardSearchResultLimit',
          ),
        ),
        summary: bounds(document.querySelector('.boardSearchResultSummary')),
        summaryScroll: document.querySelector('.boardSearchResultSummary')
          .scrollWidth,
      };
    });
    assert.ok(
      dimensions.pageWidth <= width,
      `no horizontal page overflow at ${width}: ${JSON.stringify(dimensions)}`,
    );
    assert.ok(
      dimensions.resultLimit.x > dimensions.entryOrder[1].x,
      'limit is to the right of Wierszami',
    );
    assert.ok(
      Math.abs(dimensions.resultLimit.y - dimensions.entryOrder[1].y) < 8,
      'limit stays in the radio row',
    );
    assert.ok(
      dimensions.summaryScroll <= dimensions.summary.width + 1,
      'one-line result fits',
    );
    const [undo, reset, submit] = dimensions.buttons;
    assert.ok(
      Math.abs(undo.y - reset.y) < 1 && Math.abs(reset.y - submit.y) < 1,
      'all three actions stay in one row',
    );
    assert.ok(
      submit.width > undo.width && submit.width > reset.width,
      'Search is the largest action',
    );
    assert.ok(
      Math.abs(
        dimensions.winControls[0].y +
          dimensions.winControls[0].height -
          dimensions.winControls[1].y -
          dimensions.winControls[1].height,
      ) < 1 && dimensions.winControls[1].x > dimensions.winControls[0].x,
      'range and stake fit in one row',
    );
    if (width < 520)
      assert.ok(
        dimensions.tiles.every(
          (tile) =>
            tile.width >= 50.5 && tile.width <= 55.3 && tile.height >= 50.5,
        ),
        'mobile symbol tiles have grown by 15 percent',
      );
    await page.getByRole('button', { name: 'Następna →', exact: true }).click();
    assert.match(
      await page.locator('.boardSearchResultSummary').innerText(),
      /Układ #78/,
    );
    await page
      .getByRole('combobox', { name: 'Stawka', exact: true })
      .selectOption('100');
    const chart = page.locator('.boardSearchApproximateWinChart svg');
    await chart.waitFor();
    const chartBox = await chart.boundingBox();
    await chart.click({
      position: {
        x: (chartBox.width * (72 + (200 / 2500) * 710)) / 800,
        y: chartBox.height / 2,
      },
    });
    await page.locator('.boardSearchChartPreview img').waitFor();
    assert.equal(await page.locator('#approximateWinStakeHint').count(), 0);
    await page.screenshot({
      path: path.join(output, `mobile-${width}.png`),
      fullPage: true,
    });
    checks.push({ width, ...dimensions, preview: true });
  }
  assert.deepEqual(failures, [], 'no browser errors');
  await context.close();
} finally {
  await browser.close();
  await writeFile(
    path.join(output, 'browser.json'),
    JSON.stringify({ checks, failures }, null, 2),
  );
}
console.log(
  `Compact search browser: PASS (${checks.map((check) => check.width).join('/')} px, ranked navigation, chart preview)`,
);
