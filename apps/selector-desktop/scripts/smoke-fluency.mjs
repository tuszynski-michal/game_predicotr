import { _electron as electron } from 'playwright-core';
import electronExecutable from 'electron';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile, readdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { createOwnedSmoke, hashFile } from './release-support.mjs';
import { continueFromHistory } from './ui-smoke-support.mjs';

await mkdir('.tmp', { recursive: true });
const root = await mkdtemp(path.resolve('.tmp/fluency-smoke-'));
const source = path.join(root, 'source');
const userData = path.join(root, 'user-data');
const jpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAb/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=',
  'base64',
);
const local = process.argv.includes('--local');
const executablePath = local
  ? electronExecutable
  : path.resolve(
      process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
    );
const smoke = createOwnedSmoke({
  name: 'smoke-fluency',
  fixture: root,
  tempRoot: path.resolve('.tmp'),
  userData: [userData],
});
let application;
async function launch() {
  application = await smoke.launch(electron, {
    executablePath,
    args: [...(local ? ['.'] : []), `--user-data-dir=${userData}`],
    timeout: 20000,
  });
  const page = await application.firstWindow();
  page.setDefaultTimeout(10000);
  return page;
}
async function counts(page, n) {
  await page
    .getByTestId('counts')
    .filter({ hasText: `Wybrane: ${n} ·` })
    .waitFor();
}
async function cursor(page, n) {
  await page
    .getByTestId('cursor')
    .filter({ hasText: `${n} / 6` })
    .waitFor();
}
async function ready(page) {
  await page.locator('.preview img').waitFor();
}
async function arm(mode) {
  await application.evaluate((_, mode) => {
    globalThis.fluency.mode = mode;
    globalThis.fluency.committed = false;
  }, mode);
}
async function committed() {
  for (let i = 0; i < 100; i++) {
    if (await application.evaluate(() => globalThis.fluency.committed)) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error('Native operation did not commit within 2500 ms');
}
async function release() {
  await application.evaluate(() => {
    globalThis.fluency.release?.();
    globalThis.fluency.release = null;
  });
}

try {
  await smoke.run(async () => {
    await mkdir(source);
    await mkdir(userData);
    for (let n = 1; n <= 5; n++)
      await writeFile(
        path.join(source, `photo${n}.jpg`),
        Buffer.concat([jpeg, Buffer.from(`fixture-photo-${n}`)]),
      );
    await writeFile(path.join(source, 'photo6.jpg'), 'broken jpeg');
    let page = await launch();
    await application.evaluate(({ dialog }, source) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [source],
      });
      dialog.showMessageBox = async () => ({ response: 1 });
    }, source);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Fluency');
    await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
    await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
    await cursor(page, 1);
    await ready(page);
    const bootstrap = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    // Test process only: wrap real validated IPC handlers after fixture bootstrap.
    // No application flag or operator project can enable these barriers.
    await application.evaluate(({ ipcMain }) => {
      const execute = ipcMain._invokeHandlers.get('selector:execute');
      if (typeof execute !== 'function')
        throw new Error('Electron test handler map unavailable');
      globalThis.fluency = {
        mode: '',
        committed: false,
        requests: [],
        release: null,
        snapshots: 0,
        holdSnapshot: false,
      };
      const snapshot = ipcMain._invokeHandlers.get('selector:snapshot');
      ipcMain.removeHandler('selector:snapshot');
      ipcMain.handle('selector:snapshot', async (event) => {
        const state = globalThis.fluency;
        state.snapshots++;
        if (state.holdSnapshot) {
          state.holdSnapshot = false;
          state.committed = true;
          await new Promise((resolve) => {
            state.release = resolve;
          });
        }
        return snapshot(event);
      });
      ipcMain.removeHandler('selector:execute');
      ipcMain.handle('selector:execute', async (event, request) => {
        const state = globalThis.fluency;
        state.requests.push(structuredClone(request));
        const result = await execute(event, request);
        if (result.ok) {
          const update = result.value;
          if (
            'source' in update ||
            typeof update.sourceId !== 'string' ||
            !Number.isSafeInteger(update.revision)
          )
            throw new Error(
              'execute did not return a compact workspace update',
            );
          const wire = JSON.stringify(update);
          if (
            /"(?:images|inventory|receipts|sourceRoot|relativePath)"/.test(wire)
          )
            throw new Error(
              'execute leaked source inventory or persistence internals',
            );
        }
        const mode = state.mode;
        if (
          (mode === 'navigate' && request.command.kind === 'navigate') ||
          (mode === 'crash' && request.command.kind === 'accept')
        ) {
          state.mode = '';
          state.committed = true;
          await new Promise((resolve) => {
            state.release = resolve;
          });
        }
        if (['bad-source', 'bad-project', 'old-revision'].includes(mode)) {
          state.mode = '';
          state.holdSnapshot = true;
          return {
            ...result,
            value: {
              ...result.value,
              ...(mode === 'bad-source'
                ? { sourceId: 'foreign' }
                : mode === 'bad-project'
                  ? { projectId: 'foreign' }
                  : { revision: -1 }),
            },
          };
        }
        if (mode === 'lost' && request.command.kind === 'accept') {
          state.mode = '';
          throw new Error('test-only lost response after commit');
        }
        return result;
      });
    });
    await page.locator('h1').click();
    for (const mode of ['bad-source', 'bad-project', 'old-revision']) {
      await arm(mode);
      await page.keyboard.press('ArrowRight');
      await committed(); // Snapshot fallback is deliberately held before bootstrap.
      const before = await application.evaluate(
        () => globalThis.fluency.requests.length,
      );
      await page.keyboard.press('f');
      assert.equal(
        await application.evaluate(() => globalThis.fluency.requests.length),
        before,
      );
      await release();
      await page
        .getByRole('button', { name: 'Wznów zapis', exact: true })
        .waitFor();
      await page.keyboard.press('f');
      assert.equal(
        await application.evaluate(() => globalThis.fluency.requests.length),
        before,
      );
      await page
        .getByRole('button', { name: 'Wznów zapis', exact: true })
        .click();
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll('button')].find(
            (b) => b.textContent.trim() === 'Pomiń',
          )?.disabled === false,
      );
      await page.locator('h1').click();
      await page.keyboard.press('ArrowLeft');
      await cursor(page, 1);
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll('button')].find(
            (b) => b.textContent.trim() === 'Pomiń',
          )?.disabled === false,
      );
    }
    assert.equal(
      await application.evaluate(() => globalThis.fluency.snapshots),
      3,
    );
    await application.evaluate(() => {
      globalThis.fluency.requests = [];
    });
    console.log(
      'PASS: real preload/IPC compact updates; foreign source/project and stale revision trigger snapshot and block accept before bootstrap/retry.',
    );
    await page.locator('h1').click();
    await arm('navigate');
    await page.keyboard.press('ArrowRight');
    await committed();
    await cursor(page, 2);
    await ready(page);
    assert.equal(
      (await application.evaluate(() => globalThis.fluency.requests)).length,
      1,
    );
    await page.keyboard.press('f');
    await page.getByText('Oczekuje na zapis', { exact: true }).waitFor();
    await page.keyboard.press('f');
    await page.keyboard.press('ArrowRight');
    await cursor(page, 2);
    await release();
    await counts(page, 1);
    await cursor(page, 3);
    await ready(page);
    let requests = await application.evaluate(
      () => globalThis.fluency.requests,
    );
    assert.equal(requests.filter((r) => r.command.kind === 'accept').length, 1);
    assert.equal(
      requests.find((r) => r.command.kind === 'accept').command.imageId,
      bootstrap.source.images[1].id,
    );
    console.log(
      'PASS: cached preview paints while native response is held; arrow/F pins JPEG and range; duplicate F and navigation cannot add choices.',
    );

    // Decode barrier is confined to this fixture renderer.
    await page.evaluate(() => {
      const original = HTMLImageElement.prototype.decode;
      window.fluencyDecodeRelease = null;
      HTMLImageElement.prototype.decode = async function () {
        await original.call(this);
        if (window.fluencyDecodeId && this.src.endsWith(window.fluencyDecodeId))
          await new Promise((resolve) => {
            window.fluencyDecodeRelease = resolve;
          });
      };
    });
    await page.evaluate((id) => {
      window.fluencyDecodeId = id;
    }, bootstrap.source.images[3].id);
    await page.keyboard.press('ArrowRight');
    await cursor(page, 4);
    await page.keyboard.press('f');
    await page.getByText('Oczekuje na zapis', { exact: true }).waitFor();
    await page
      .getByRole('button', { name: 'Anuluj oczekiwanie', exact: true })
      .click();
    await page.evaluate(() => {
      window.fluencyDecodeId = '';
      window.fluencyDecodeRelease?.();
    });
    await ready(page);
    await counts(page, 1);
    await page.locator('h1').click();
    await arm('lost');
    await page.keyboard.press('Enter');
    await counts(page, 2);
    await cursor(page, 5);
    await ready(page);
    requests = await application.evaluate(() => globalThis.fluency.requests);
    const lastTwo = requests
      .filter((r) => r.command.kind === 'accept')
      .slice(-2);
    assert.equal(lastTwo.length, 2);
    assert.deepEqual(lastTwo[0], lastTwo[1]);
    assert.equal(lastTwo[0].command.imageId, bootstrap.source.images[3].id);
    console.log(
      'PASS: F before decode is cancellable; Enter uses same path; lost response retries identical operationId exactly once.',
    );

    await arm('crash');
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
      .click();
    await committed();
    const child = application.process();
    const exited = new Promise((resolve) => child.once('exit', resolve));
    execFileSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      timeout: 5000,
      windowsHide: true,
      stdio: 'ignore',
    });
    await exited;
    page = await launch();
    await continueFromHistory(page);
    await counts(page, 3);
    const recovered = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    assert.equal(recovered.projectId, bootstrap.projectId);
    assert.equal(recovered.nextRangeStart, 28);
    assert.equal(recovered.acceptedCount, 3);
    assert.deepEqual(
      recovered.acceptedImageIds,
      [1, 3, 4].map((i) => recovered.source.images[i].id),
    );
    const output = path.join(root, 'Fluency a1 1-500000');
    const manifest = JSON.parse(
      await readFile(
        path.join(output, 'manual-image-selection-output-v1.json'),
        'utf8',
      ),
    );
    assert.equal(manifest.nextRangeStart, 28);
    assert.equal(
      manifest.decisions.filter((decision) => decision.action === 'accepted')
        .length,
      3,
    );
    const files = (await readdir(output))
      .filter((file) => file.endsWith('.jpg'))
      .sort();
    assert.deepEqual(files, ['seq_1-9.jpg', 'seq_10-18.jpg', 'seq_19-27.jpg']);
    for (const [index, file] of files.entries())
      assert.equal(
        await hashFile(path.join(output, file)),
        await hashFile(path.join(source, `photo${[2, 4, 5][index]}.jpg`)),
      );
    console.log(
      'PASS: crash after native commit and before response preserves three decisions, exact JPEGs, numbering and manifest in a new process.',
    );

    await page.locator('h1').click();
    await page.keyboard.press('ArrowRight');
    await cursor(page, 6);
    await page
      .getByText('Nie można odczytać JPEG-a.', { exact: false })
      .waitFor();
    await page.keyboard.press('f');
    await page
      .getByText('Nie zapisano — nie można odczytać JPEG-a.', { exact: true })
      .waitFor();
    await counts(page, 3);
    await page.evaluate((target) => {
      const original = HTMLImageElement.prototype.decode;
      HTMLImageElement.prototype.decode = async function () {
        await original.call(this);
        if (this.src.endsWith(target))
          await new Promise((resolve) => {
            window.fluencyDecodeRelease = resolve;
          });
      };
      for (let i = 0; i < 3; i++)
        window.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }),
        );
    }, recovered.source.images[2].id);
    await cursor(page, 3);
    await page.keyboard.press('f');
    await page.getByText('Oczekuje na zapis', { exact: true }).waitFor();
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].close(),
    );
    await page.getByText('Oczekuje wybór.', { exact: false }).waitFor();
    assert.equal(application.windows().length, 1);
    await page
      .getByRole('button', { name: 'Anuluj oczekiwanie', exact: true })
      .click();
    await application.evaluate(({ ipcMain }) => {
      globalThis.fluencyShutdownReady = ipcMain._invokeHandlers.get(
        'selector:shutdown-ready',
      );
      ipcMain.removeHandler('selector:shutdown-ready');
      ipcMain.handle('selector:shutdown-ready', async () => ({
        ok: true,
        value: undefined,
      }));
    });
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].close(),
    );
    await page
      .getByText('Nie zamknięto — przekroczono czas oczekiwania.', {
        exact: false,
      })
      .waitFor({ timeout: 15000 });
    assert.equal(application.windows().length, 1);
    assert.equal(
      (await page.evaluate(() => window.selector.snapshot())).value.projectId,
      bootstrap.projectId,
    );
    const lockPath = path.join(
      root,
      'source selekcja',
      'selector-project.lock',
    );
    assert.ok((await readFile(lockPath)).length);
    await application.evaluate(({ ipcMain }) => {
      ipcMain.removeHandler('selector:shutdown-ready');
      ipcMain.handle(
        'selector:shutdown-ready',
        globalThis.fluencyShutdownReady,
      );
    });
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].close(),
    );
    await page.waitForEvent('close');
    await assert.rejects(readFile(lockPath), { code: 'ENOENT' });
    const finalManifest = JSON.parse(
      await readFile(
        path.join(output, 'manual-image-selection-output-v1.json'),
        'utf8',
      ),
    );
    assert.equal(finalManifest.currentIndex, 2);
    console.log(
      'PASS: unsent F prevents window close; handshake timeout preserves window/project/lock; retry closes and flushes final cursor before lock release.',
    );
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
