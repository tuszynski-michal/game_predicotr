// Renderer-only checks for hosts that cannot launch Electron/CIM. Native
// persistence is tested separately by renderer-contracts.test.mjs.
import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const jpeg = await readFile('test/fixtures/preview-800x600.jpg');
let workspace = null;
let active = false;
let fullscreen = false;
let browser;
let page;
const source = {
  id: 'fixture-source',
  name: 'source',
  images: Array.from({ length: 4 }, (_, index) => ({
    id: `photo${index + 1}`,
    name: `photo${index + 1}.jpg`,
    relativePath: `photo${index + 1}.jpg`,
    size: jpeg.length,
    lastModified: 0,
    url: `http://localhost/photos/photo${index + 1}`,
  })),
};
const ok = (value) => ({ ok: true, value });
async function launch() {
  browser = await chromium.launch({
    executablePath:
      process.argv[2] ??
      'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1000 },
  });
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) =>
    console.error('Renderer error:', error.message),
  );
  await page.route('http://localhost/**', async (route) => {
    const name = new URL(route.request().url()).pathname;
    if (name.startsWith('/photos/'))
      return route.fulfill({ contentType: 'image/jpeg', body: jpeg });
    const file = name === '/' ? 'index.html' : name.slice(1);
    assert.ok(['index.html', 'app.js', 'app.css'].includes(file));
    await route.fulfill({
      contentType: file.endsWith('.js')
        ? 'application/javascript'
        : file.endsWith('.css')
          ? 'text/css'
          : 'text/html',
      body: await readFile(path.join('dist/renderer', file)),
    });
  });
  await page.exposeFunction('fixtureInvoke', (name, ...args) => {
    if (name === 'recent')
      return ok(
        workspace
          ? [
              {
                projectId: workspace.projectId,
                name: 'Overlay fixture',
                openedAt: '2026-11-16T00:00:00.000Z',
              },
            ]
          : [],
      );
    if (name === 'games') return ok(['Overlay']);
    if (name === 'begin')
      return ok({
        kind: 'new',
        draft: {
          sourceToken: 'fixture',
          sourceName: 'source',
          sourcePath: 'D:/fixture/source',
          projectPath: 'D:/fixture/project',
          outputParentPath: 'D:/fixture',
        },
      });
    if (name === 'create') {
      workspace = {
        projectId: 'fixture-project',
        revision: 0,
        source,
        sourceName: 'source',
        projectName: 'Overlay',
        outputName: 'result',
        currentImageId: source.images[0].id,
        gameName: 'Overlay',
        gameUpdate: 'a1',
        firstLayout: 1,
        direction: 'ascending',
        sequenceUpperBound: 500000,
        nextRangeStart: 1,
        selectionComplete: false,
        acceptedCount: 0,
        skippedCount: 0,
        acceptedImageIds: [],
        decisionCount: 0,
        issue: null,
        view: { navigationStep: 1, zoom: 100, scrollX: 0, scrollY: 0 },
      };
      active = true;
      return ok(workspace);
    }
    if (name === 'continue') {
      active = true;
      return ok(workspace);
    }
    if (name === 'snapshot') return ok(active ? workspace : null);
    if (name === 'saveView') {
      workspace.view = structuredClone(args[1]);
      return ok();
    }
    if (name === 'fullscreen') {
      fullscreen = !fullscreen;
      return ok(fullscreen);
    }
    if (name === 'close') {
      active = false;
      return ok();
    }
    if (name === 'execute') {
      const command = args[0].command;
      workspace.revision++;
      if (command.kind === 'navigate')
        workspace.currentImageId = command.imageId;
      else if (command.kind === 'skip') {
        workspace.nextRangeStart += 9;
        workspace.skippedCount++;
        workspace.decisionCount++;
      } else throw new Error(`Unexpected fixture command: ${command.kind}`);
      const { source: omitted, ...update } = workspace;
      return ok({ ...update, sourceId: omitted.id });
    }
    throw new Error(`Unexpected fixture IPC: ${name}`);
  });
  await page.addInitScript(() => {
    const names = [
      'recent',
      'games',
      'begin',
      'create',
      'continue',
      'snapshot',
      'saveView',
      'execute',
      'close',
      'fullscreen',
    ];
    window.selector = Object.fromEntries(
      names.map((name) => [
        name,
        (...args) => window.fixtureInvoke(name, ...args),
      ]),
    );
    for (const name of [
      'onFullscreenChanged',
      'onShutdownRequested',
      'onShutdownCancelled',
    ])
      window.selector[name] = () => () => {};
  });
  await page.goto('http://localhost/');
  return page;
}
async function ready(page) {
  await page.waitForFunction(
    () =>
      document.querySelector('.preview img')?.naturalWidth > 0 &&
      !document.querySelector('.image-loading'),
  );
}
async function drag(page, locator, dx, dy) {
  const box = await locator.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + dx,
    box.y + box.height / 2 + dy,
    { steps: 6 },
  );
  await page.mouse.up();
}
try {
  page = await launch();
  await page
    .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
    .click();
  await page.getByLabel('Nazwa gry', { exact: true }).fill('Overlay');
  await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
  await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
  await ready(page);
  const overlay = page.getByTestId('range-overlay');
  await page.getByLabel('Zakres na zdjęciu', { exact: true }).check();
  await overlay.waitFor();
  assert.equal(await overlay.locator('span').textContent(), 'Zakres: 1–9');
  assert.deepEqual(
    await overlay.evaluate((e) => [
      getComputedStyle(e).color,
      getComputedStyle(e).backgroundColor,
    ]),
    ['rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)'],
  );
  await drag(page, overlay.locator('span'), 90, 55);
  assert.ok(workspace.view.rangeOverlay.x > 0.1);
  await drag(
    page,
    page.getByRole('button', {
      name: 'Zmień rozmiar napisu zakresu',
      exact: true,
    }),
    50,
    20,
  );
  assert.ok(workspace.view.rangeOverlay.fontSize > 32);
  const configured = structuredClone(workspace.view.rangeOverlay);
  await page.getByLabel('Zakres na zdjęciu', { exact: true }).uncheck();
  await overlay.waitFor({ state: 'detached' });
  await page.getByLabel('Zakres na zdjęciu', { exact: true }).check();
  assert.deepEqual(workspace.view.rangeOverlay, configured);
  await page
    .getByRole('button', { name: 'Pełny ekran (F11)', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Reset napisu', exact: true })
    .waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Wyjdź (F11)', exact: true }).click();
  await page.getByRole('button', { name: 'Pomiń', exact: true }).click();
  await page.waitForFunction(
    () =>
      document.querySelector('[data-testid="range-overlay"] span')
        ?.textContent === 'Zakres: 10–18',
  );
  console.log(
    'PASS browser renderer: white/transparent text, drag, corner resize, toggle memory, fullscreen layout and range update.',
  );
  await page.getByLabel('Zoom', { exact: true }).selectOption('300');
  await page.locator('.preview').evaluate((e) => {
    e.scrollLeft = 120;
    e.scrollTop = 100;
    e.dispatchEvent(new Event('scroll'));
  });
  await page.waitForFunction(
    async () => (await window.selector.snapshot()).value.view.scrollY === 100,
  );
  await page.evaluate(() => {
    const decode = HTMLImageElement.prototype.decode;
    window.warmRelease = null;
    HTMLImageElement.prototype.decode = async function () {
      await decode.call(this);
      if (this.src.endsWith('photo2'))
        await new Promise((resolve) => {
          window.warmRelease = resolve;
        });
    };
    window.badFrames = 0;
    window.sample = true;
    const frame = () => {
      if (!window.sample) return;
      const image = document.querySelector('.preview img');
      const viewport = document.querySelector('.preview');
      if (
        !image?.complete ||
        !image.naturalWidth ||
        viewport.scrollLeft !== 120 ||
        viewport.scrollTop !== 100
      )
        window.badFrames++;
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
  const previous = await page.locator('.preview img').getAttribute('src');
  await page.locator('h1').click();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => typeof window.warmRelease === 'function');
  assert.equal(
    await page.locator('.preview img').getAttribute('src'),
    previous,
  );
  await page.evaluate(() => window.warmRelease());
  await ready(page);
  assert.notEqual(
    await page.locator('.preview img').getAttribute('src'),
    previous,
  );
  assert.equal(
    await page.evaluate(() => {
      window.sample = false;
      return window.badFrames;
    }),
    0,
  );
  console.log(
    'PASS browser renderer: held warm decode retains old image; no empty DOM frames or scroll jumps at 300%.',
  );
  await browser.close();
  page = await launch();
  await page
    .getByLabel('Ostatnie projekty', { exact: true })
    .selectOption(workspace.projectId);
  await page.getByRole('button', { name: 'Kontynuuj', exact: true }).click();
  await ready(page);
  assert.deepEqual(workspace.view.rangeOverlay, configured);
  await page.getByRole('button', { name: 'Reset napisu', exact: true }).click();
  assert.deepEqual(workspace.view.rangeOverlay, {
    enabled: true,
    x: 0.05,
    y: 0.05,
    fontSize: 32,
  });
  assert.equal(workspace.view.zoom, 300);
  console.log(
    'PASS browser renderer: new browser process consumes saved IPC fixture preferences; reset preserves zoom and enabled state.',
  );
} catch (error) {
  console.error('Renderer fixture state:', JSON.stringify(workspace));
  if (page && !page.isClosed())
    console.error(await page.locator('main').innerText());
  throw error;
} finally {
  await browser?.close();
}
