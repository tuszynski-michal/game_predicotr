import { waitForHistory, continueFromHistory } from './ui-smoke-support.mjs';
import { _electron as electron, chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { createOwnedSmoke, boundedSmokeStep } from './release-support.mjs';
const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
await mkdir('.tmp', { recursive: true });
const fixture = await mkdtemp(path.resolve('.tmp/ux-smoke-'));
const source = path.join(fixture, 'source');
const userData = path.join(fixture, 'user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-ux',
  fixture: fixture,
  tempRoot: path.resolve('.tmp'),
  userData: [userData],
});
let application;
let page;
let reopenedBrowser;
async function launch(extraArgs = []) {
  application = await smoke.launch(electron, {
    executablePath,
    args: [`--user-data-dir=${userData}`, ...extraArgs],
    timeout: 20000,
  });
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(15000);
  assert.equal(
    await application.evaluate(({ app }) => app.getPath('userData')),
    userData,
  );
  await application.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [directory],
    });
    dialog.showMessageBox = async () => ({
      response: 1,
      checkboxChecked: false,
    });
  }, source);
}
async function secondLaunch() {
  const child = smoke.registerProcess(
    spawn(executablePath, [`--user-data-dir=${userData}`], {
      windowsHide: true,
      stdio: 'ignore',
    }),
  );
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error('Second instance did not exit within 10 seconds'));
    }, 10000);
    child.once('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

async function verifyDeferredRelaunch() {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  const evidencePath = path.join(fixture, 'relaunch-evidence.json');
  await launch([`--remote-debugging-port=${port}`]);
  const oldPid = application.process().pid;
  await application.evaluate(({ app, BrowserWindow }, evidencePath) => {
    const fs = process.getBuiltinModule('fs');
    const relaunch = app.relaunch.bind(app);
    const evidence = {
      requests: 0,
      relaunches: [],
      args: process.argv.slice(1),
    };
    app.on('second-instance', () => {
      evidence.requests++;
      fs.writeFileSync(evidencePath, JSON.stringify(evidence));
    });
    app.relaunch = (options) => {
      evidence.relaunches.push(options);
      fs.writeFileSync(evidencePath, JSON.stringify(evidence));
      relaunch(options);
    };
    const window = BrowserWindow.getAllWindows()[0];
    // Hold the final window close so two real launches arrive during shutdown.
    // Production close and disposal still execute through their normal handlers.
    let released = false;
    window.on('close', (event) => {
      if (!released) event.preventDefault();
    });
    setTimeout(() => {
      released = true;
      window.close();
    }, 5000);
    window.close();
  }, evidencePath);
  const exited = application.waitForEvent('close', { timeout: 15000 });
  await secondLaunch();
  await secondLaunch();
  await exited;
  application = null;
  const evidence = JSON.parse(await readFile(evidencePath, 'utf8'));
  assert.equal(evidence.requests, 2);
  assert.equal(evidence.relaunches.length, 1);
  assert.deepEqual(evidence.relaunches[0].args, evidence.args);
  assert.ok(evidence.args.includes(`--user-data-dir=${userData}`));
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      reopenedBrowser = await chromium.connectOverCDP(
        `http://127.0.0.1:${port}`,
        { timeout: 1000 },
      );
      break;
    } catch (error) {
      if (attempt === 19) throw error;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  const session = await reopenedBrowser.newBrowserCDPSession();
  const { processInfo } = await session.send('SystemInfo.getProcessInfo');
  const relaunchedPid = processInfo.find(
    (entry) => entry.type === 'browser',
  )?.id;
  smoke.registerPid(relaunchedPid);
  assert.notEqual(relaunchedPid, oldPid);
  const windows = reopenedBrowser
    .contexts()
    .flatMap((context) => context.pages());
  assert.equal(windows.length, 1);
  await waitForHistory(windows[0]);
  const diagnostic = await readFile(
    path.join(userData, 'logs', 'selector.log'),
    'utf8',
  );
  assert.ok(diagnostic.includes('application-start'));
  // Close only the relaunched fixture's window through Electron's normal close.
  await windows[0].close();
  await boundedSmokeStep(() => reopenedBrowser.close());
  reopenedBrowser = null;
  console.log(
    'PASS: two real EXE launches during close produce one deferred process/window and preserve user-data arguments.',
  );
}
async function ready() {
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return image?.complete && image.naturalWidth > 0;
  });
  await page.waitForFunction(
    () => document.querySelector('main')?.getAttribute('aria-busy') === 'false',
  );
}
async function assertCentered() {
  await page.waitForFunction(() => {
    const preview = document.querySelector('.preview');
    const image = preview?.querySelector('img');
    if (!image?.complete || !image.naturalWidth) return false;
    const outer = preview.getBoundingClientRect();
    const inner = image.getBoundingClientRect();
    return (
      Math.abs(
        inner.x + inner.width / 2 - (outer.x + preview.clientWidth / 2),
      ) < 2 &&
      Math.abs(
        inner.y + inner.height / 2 - (outer.y + preview.clientHeight / 2),
      ) < 2
    );
  });
}
async function assertRangeCentered() {
  const layout = await page.evaluate(() => {
    const range = document.querySelector('.range-indicator strong');
    const label = range.getBoundingClientRect();
    const photo = document.querySelector('.preview').getBoundingClientRect();
    const toolbar = document
      .querySelector('.viewer-toolbar')
      .getBoundingClientRect();
    return {
      offset: Math.abs(label.x + label.width / 2 - (photo.x + photo.width / 2)),
      abovePhoto: label.bottom <= photo.top,
      belowToolbar: label.top >= toolbar.bottom,
      inToolbar: Boolean(range.closest('nav')),
    };
  });
  assert.ok(
    layout.offset < 1,
    `Range is not centered over photo: ${JSON.stringify(layout)}`,
  );
  assert.ok(layout.abovePhoto && layout.belowToolbar);
  assert.equal(layout.inToolbar, false);
}
try {
  await smoke.run(async () => {
    await mkdir(source);
    await mkdir(userData);

    await launch();
    assert.equal(
      await page.evaluate(() => 'pickSource' in window.selector),
      false,
    );
    const jpeg = Buffer.from(
      await application.evaluate(({ nativeImage }) =>
        nativeImage
          .createFromBitmap(Buffer.alloc(800 * 600 * 4, 140), {
            width: 800,
            height: 600,
          })
          .toJPEG(80)
          .toString('base64'),
      ),
      'base64',
    );
    const portrait = Buffer.from(
      await application.evaluate(({ nativeImage }) =>
        nativeImage
          .createFromBitmap(Buffer.alloc(400 * 800 * 4, 140), {
            width: 400,
            height: 800,
          })
          .toJPEG(80)
          .toString('base64'),
      ),
      'base64',
    );
    for (let i = 1; i <= 3; i++)
      await writeFile(
        path.join(source, `photo${i}.jpg`),
        i === 2 ? portrait : jpeg,
      );
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Mumie');
    assert.equal(await page.getByRole('checkbox').count(), 0);
    await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
    await ready();
    await assertCentered();
    await assertRangeCentered();
    await page.evaluate(() => {
      const top = document
        .querySelector('.preview')
        .getBoundingClientRect().top;
      window.previewTops = [top];
      window.layoutObserver = new MutationObserver(() =>
        window.previewTops.push(
          document.querySelector('.preview').getBoundingClientRect().top,
        ),
      );
      window.layoutObserver.observe(document.querySelector('main'), {
        subtree: true,
        childList: true,
        attributes: true,
      });
    });
    await page.locator('h1').click();
    await page.keyboard.press('ArrowRight');
    await page.getByTestId('cursor').filter({ hasText: '2 / 3' }).waitFor();
    await ready();
    const tops = await page.evaluate(() => {
      window.layoutObserver.disconnect();
      return window.previewTops;
    });
    assert.ok(
      Math.max(...tops) - Math.min(...tops) < 1,
      `Preview moved during navigation: ${tops}`,
    );
    assert.equal(
      await page
        .getByText('Pozycja zdjęcia zapisana.', { exact: true })
        .count(),
      0,
    );
    assert.equal(await page.locator('main [role="status"]').count(), 0);
    await assertCentered();
    await page
      .getByRole('button', { name: 'Pełny ekran (F11)', exact: true })
      .click();
    await page.locator('main.fullscreen').waitFor();
    await assertCentered();
    await assertRangeCentered();
    const fullscreenLayout = await page.evaluate(() => {
      const preview = document
        .querySelector('.preview')
        .getBoundingClientRect();
      const toolbar = document
        .querySelector('.viewer-toolbar')
        .getBoundingClientRect();
      const visibleButtons = [...document.querySelectorAll('button')]
        .filter((button) => button.getClientRects().length > 0)
        .map((button) => button.textContent.trim());
      return {
        height: preview.height,
        top: preview.top,
        bottom: preview.bottom,
        viewport: innerHeight,
        toolbarBottom: toolbar.bottom,
        visibleButtons,
      };
    });
    assert.deepEqual(fullscreenLayout.visibleButtons, ['Wyjdź (F11)']);
    assert.ok(fullscreenLayout.height > fullscreenLayout.viewport * 0.8);
    assert.ok(
      Math.abs(fullscreenLayout.bottom - (fullscreenLayout.viewport - 8)) < 1,
    );
    assert.ok(fullscreenLayout.top >= fullscreenLayout.toolbarBottom);
    await page
      .getByTestId('fullscreen-counts')
      .filter({ hasText: 'Wybrane: 0' })
      .waitFor();
    await page
      .getByTestId('fullscreen-range')
      .filter({ hasText: 'Zakres: 1–9' })
      .waitFor();
    await page.locator('.preview').click();
    await page.keyboard.press('ArrowLeft');
    await page.getByTestId('cursor').filter({ hasText: '1 / 3' }).waitFor();
    await ready();
    await assertCentered();
    await page.keyboard.press('ArrowRight');
    await page.getByTestId('cursor').filter({ hasText: '2 / 3' }).waitFor();
    await ready();
    const screenshots = path.resolve('../../artifacts/selector-layout-0.1.6');
    await mkdir(screenshots, { recursive: true });
    await page.screenshot({ path: path.join(screenshots, 'fullscreen.png') });
    await page
      .getByRole('button', {
        name: 'Wyjdź (F11)',
        exact: true,
      })
      .click();
    await page.getByRole('button', { name: 'Zakres', exact: true }).waitFor();
    await page.keyboard.press('F11');
    await page.locator('main.fullscreen').waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Zakres', exact: true }).waitFor();
    // Changes through the native window must update the renderer too.
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setFullScreen(true),
    );
    await page.locator('main.fullscreen').waitFor();
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setFullScreen(false),
    );
    await page.getByRole('button', { name: 'Zakres', exact: true }).waitFor();
    await assertCentered();
    await assertRangeCentered();
    await page.screenshot({ path: path.join(screenshots, 'windowed.png') });
    console.log(
      'PASS: quiet/stable navigation; landscape and portrait centering; minimal native fullscreen, keyboard navigation, button/F11/Escape/native exit.',
    );
    assert.equal(
      (await page.evaluate(() => window.selector.snapshot())).value
        .acceptedCount,
      0,
    );
    await page.getByLabel('Zoom', { exact: true }).selectOption('1000');
    await page.waitForFunction(() => {
      const preview = document.querySelector('.preview');
      return preview.scrollWidth > preview.clientWidth;
    });
    const finalScroll = await page.locator('.preview').evaluate((preview) => {
      for (let i = 0; i < 50; i++) {
        preview.scrollLeft = i;
        preview.scrollTop = i * 2;
        preview.dispatchEvent(new Event('scroll'));
      }
      return { scrollX: preview.scrollLeft, scrollY: preview.scrollTop };
    });
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
      .click();
    await page
      .getByTestId('counts')
      .filter({ hasText: 'Wybrane: 1' })
      .waitFor();
    await ready();
    const current = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    assert.equal(current.view.scrollX, finalScroll.scrollX);
    assert.equal(current.view.scrollY, finalScroll.scrollY);
    // Browser scroll events arriving after Close must not overwrite the last view.
    await page.evaluate(() => {
      document.addEventListener(
        'click',
        () => {
          const preview = document.querySelector('.preview');
          preview.scrollLeft += 180;
          preview.dispatchEvent(new Event('scroll'));
        },
        { once: true },
      );
    });
    await page.getByRole('button', { name: 'Zamknij projekt' }).click();
    await waitForHistory(page);
    const savedView = JSON.parse(
      await readFile(
        path.join(userData, 'views', `${current.projectId}.json`),
        'utf8',
      ),
    );
    assert.deepEqual(savedView, current.view);
    await application.evaluate(({ dialog }, directory) => {
      dialog.showOpenDialog = async () => {
        await new Promise((resolve) => setTimeout(resolve, 300));
        return { canceled: false, filePaths: [directory] };
      };
    }, `${source} selekcja`);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page
      .getByText('Weryfikacja źródła i sum kontrolnych JPEG-ów…', {
        exact: true,
      })
      .waitFor();
    await ready();
    await smoke.close(application);
    application = null;
    await launch();
    await continueFromHistory(page);
    await ready();
    const reopened = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    assert.equal(reopened.acceptedCount, 1);
    assert.deepEqual(reopened.view, savedView);
    await page.waitForFunction((expected) => {
      const preview = document.querySelector('.preview');
      return (
        preview.scrollLeft === expected.scrollX &&
        preview.scrollTop === expected.scrollY
      );
    }, finalScroll);
    console.log(
      'PASS: removed picker, open verification, quiet navigation, scroll burst with accept, project-close flush and new-process view/decisions.',
    );
    const closingScroll = await page.locator('.preview').evaluate((preview) => {
      preview.scrollLeft = 120;
      preview.scrollTop = 160;
      preview.dispatchEvent(new Event('scroll'));
      return { scrollX: preview.scrollLeft, scrollY: preview.scrollTop };
    });
    const lockPath = `${source} selekcja/selector-project.lock`;
    const foreign = JSON.parse(await readFile(lockPath, 'utf8'));
    foreign.ownerId = randomUUID();
    const foreignBytes = Buffer.from(JSON.stringify(foreign));
    await writeFile(lockPath, foreignBytes);
    const exited = application.waitForEvent('close', { timeout: 15000 });
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].close(),
    );
    await exited;
    application = null;
    assert.deepEqual(await readFile(lockPath), foreignBytes);
    const closedView = JSON.parse(
      await readFile(
        path.join(userData, 'views', `${current.projectId}.json`),
        'utf8',
      ),
    );
    assert.equal(closedView.scrollX, closingScroll.scrollX);
    assert.equal(closedView.scrollY, closingScroll.scrollY);
    const log = await readFile(
      path.join(userData, 'logs', 'selector.log'),
      'utf8',
    );
    assert.match(log, /LOCK_LOST/);
    console.log(
      'PASS: real window/process closes after LOCK_LOST, flushes last view, logs diagnostic and preserves foreign lock bytes.',
    );
    await verifyDeferredRelaunch();
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish({
    teardown: async () => {
      if (reopenedBrowser) {
        for (const context of reopenedBrowser.contexts())
          for (const window of context.pages())
            await boundedSmokeStep(() => window.close());
        await boundedSmokeStep(() => reopenedBrowser.close());
      }
    },
  });
}
