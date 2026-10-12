import { waitForHistory, continueFromHistory } from './ui-smoke-support.mjs';
import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  writeFile,
  rename,
  cp,
  readFile,
} from 'node:fs/promises';
import path from 'node:path';
import { removeOwnedTemp } from './release-support.mjs';
let executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
await mkdir('.tmp', { recursive: true });
const fixture = await mkdtemp(path.resolve('.tmp/ui-smoke-'));
const source = path.join(fixture, 'source');
const userData = path.join(fixture, 'user-data');
await mkdir(source);
await mkdir(userData);
let application;
let page;
const provenancePath = process.argv
  .find((value) => value.startsWith('--release-metadata='))
  ?.slice('--release-metadata='.length);
const provenance = provenancePath
  ? JSON.parse(await readFile(provenancePath, 'utf8'))
  : null;
async function launch() {
  application = await electron.launch({
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  assert.equal(
    await application.evaluate(({ app }) => app.getPath('userData')),
    userData,
  );
  if (provenance) {
    const built = await application.evaluate(({ app }) => {
      const fs = process.getBuiltinModule('fs');
      return {
        version: app.getVersion(),
        info: JSON.parse(
          fs.readFileSync(`${app.getAppPath()}/dist/build-info.json`, 'utf8'),
        ),
      };
    });
    assert.equal(built.version, provenance.applicationVersion);
    assert.equal(built.info.sourceCommit, provenance.sourceCommit);
    assert.equal(built.info.dirty, provenance.dirty);
    assert.equal(built.info.builtAt, provenance.builtAt);
  }
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(20000);
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
async function snapshot() {
  const result = await page.evaluate(() => window.selector.snapshot());
  assert.equal(result.ok, true);
  return result.value;
}
async function waitState(predicate) {
  const deadline = Date.now() + 20000;
  do {
    const state = await snapshot();
    if (predicate(state)) return state;
    await new Promise((resolve) => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  throw new Error('Timed out waiting for durable project state');
}
async function settled() {
  await page.waitForFunction(
    () =>
      !document.querySelector('.save-state')?.textContent?.includes('w toku'),
  );
}
async function imageReady() {
  await page.waitForFunction(() => {
    const i = document.querySelector('.preview img');
    return i?.complete && i.naturalWidth > 0;
  });
  await settled();
}
async function bodyKey(key) {
  await page.locator('h1').click();
  await page.keyboard.press(key);
  await settled();
}
try {
  await launch();
  const jpeg = await application.evaluate(({ nativeImage }) =>
    nativeImage
      .createFromBitmap(Buffer.alloc(800 * 600 * 4, 180), {
        width: 800,
        height: 600,
      })
      .toJPEG(80)
      .toString('base64'),
  );
  for (let n = 1; n <= 8; n++)
    await writeFile(
      path.join(source, `photo${n}.jpg`),
      Buffer.from(jpeg, 'base64'),
    );
  await page
    .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
    .click();
  await page.getByLabel('Nazwa gry', { exact: true }).fill('Mumie');
  await page.screenshot({ path: path.resolve('.tmp/ui-start.png') });
  await page.getByLabel('Ostatnia plansza', { exact: true }).fill('30');
  await page.getByRole('checkbox', { name: /Projekt i wynik będą/ }).check();
  await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
  await imageReady();
  console.log('PASS: isolated project created and JPEG decoded.');
  let state = await snapshot();
  assert.equal(state.acceptedCount, 0);
  assert.equal(state.nextRangeStart, 1);
  assert.equal(
    await page.locator('.preview img').evaluate((i) => i.naturalWidth),
    800,
  );
  await page.getByLabel('Skok', { exact: true }).selectOption('15');
  await page.getByLabel('Zoom', { exact: true }).selectOption('1000');
  await page.locator('.preview').evaluate((e) => {
    e.scrollLeft = 120;
    e.scrollTop = 100;
    e.dispatchEvent(new Event('scroll'));
  });
  await waitState(
    (state) => state.view.scrollX === 120 && state.view.scrollY === 100,
  );
  await bodyKey('Enter');
  await waitState((state) => state.acceptedCount === 1);
  await imageReady();
  state = await snapshot();
  assert.equal(
    state.source.images.findIndex((i) => i.id === state.currentImageId),
    1,
  );
  assert.equal(state.nextRangeStart, 10);
  await bodyKey('Tab');
  await waitState((state) => state.skippedCount === 1);
  state = await snapshot();
  assert.equal(
    state.source.images.findIndex((i) => i.id === state.currentImageId),
    1,
  );
  assert.equal(state.nextRangeStart, 19);
  await page.locator('h1').click();
  const beforeRepeats = await snapshot();
  for (const key of ['Enter', 'f', 'F', 'Tab', 'Control+z', 'a']) {
    const consumed = await page.evaluate((key) => {
      const event = new KeyboardEvent('keydown', {
        key: key === 'Control+z' ? 'z' : key,
        ctrlKey: key === 'Control+z',
        repeat: true,
        cancelable: true,
        bubbles: true,
      });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }, key);
    assert.equal(
      consumed,
      true,
      `${key} repeat must suppress browser defaults`,
    );
    await settled();
    const afterRepeat = await snapshot();
    assert.equal(afterRepeat.revision, beforeRepeats.revision);
    assert.equal(afterRepeat.acceptedCount, beforeRepeats.acceptedCount);
    assert.equal(afterRepeat.skippedCount, beforeRepeats.skippedCount);
    assert.equal(afterRepeat.currentImageId, beforeRepeats.currentImageId);
  }
  await page.getByLabel('Skok', { exact: true }).selectOption('1');
  await waitState((state) => state.view.navigationStep === 1);
  await page.evaluate(() =>
    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', repeat: true }),
    ),
  );
  await waitState(
    (state) => state.currentImageId !== beforeRepeats.currentImageId,
  );
  await imageReady();
  await page.evaluate(() =>
    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowLeft', repeat: true }),
    ),
  );
  await waitState(
    (state) => state.currentImageId === beforeRepeats.currentImageId,
  );
  await imageReady();
  await page
    .getByLabel('Skok', { exact: true })
    .selectOption(String(beforeRepeats.view.navigationStep));
  await waitState(
    (state) => state.view.navigationStep === beforeRepeats.view.navigationStep,
  );
  await page
    .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
    .evaluate((e) => {
      e.click();
      e.click();
    });
  await waitState((state) => state.acceptedCount === 2);
  await imageReady();
  const advanced = await snapshot();
  assert.equal(
    advanced.source.images.findIndex((i) => i.id === advanced.currentImageId),
    2,
  );
  assert.equal((await snapshot()).nextRangeStart, 28);
  await bodyKey('Control+z');
  await waitState((state) => state.acceptedCount === 1);
  await imageReady();
  await page.getByRole('button', { name: 'Pełny ekran (F11)' }).click();
  assert.equal(
    await application.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].isFullScreen(),
    ),
    true,
  );
  await page.keyboard.press('F11');
  await page.getByRole('button', { name: 'Zmień zakres' }).click();
  await page.getByLabel('Początek zakresu', { exact: true }).fill('28');
  await page.getByLabel('Początek zakresu', { exact: true }).press('f');
  assert.equal((await snapshot()).acceptedCount, 1);
  await page.getByRole('button', { name: 'Anuluj zakres' }).click();
  await page
    .getByRole('button', { name: 'Restart partii', exact: true })
    .click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button', { name: 'Anuluj restart' }).click();
  assert.equal((await snapshot()).decisionCount, 2);
  await page.locator('.preview').evaluate((e) => {
    e.scrollLeft = 120;
    e.scrollTop = 100;
    e.dispatchEvent(new Event('scroll'));
  });
  const beforeClose = await snapshot();
  console.log(
    'PASS: shortcuts, undo, repeat/double-submit, fullscreen and view changes.',
  );
  await page.getByRole('button', { name: 'Zamknij projekt' }).click();
  await waitForHistory(page);
  await application.close();
  application = null;
  if (process.argv.includes('--relocate-program')) {
    const originalProgram = path.dirname(executablePath);
    const relocatedProgram = path.join(
      path.dirname(originalProgram),
      'program-updated-location',
    );
    // Only the release harness opts in and creates this program folder under .tmp.
    const ownedTemp = path.resolve('.tmp');
    const relative = path.relative(ownedTemp, originalProgram);
    assert.ok(
      relative && !relative.startsWith('..') && !path.isAbsolute(relative),
    );
    await cp(originalProgram, relocatedProgram, {
      recursive: true,
      errorOnExist: true,
      force: false,
    });
    executablePath = path.join(relocatedProgram, path.basename(executablePath));
    console.log(
      'PASS: launching copied same-version program from changed location.',
    );
  }
  await launch();
  await continueFromHistory(page);
  await imageReady();
  state = await snapshot();
  assert.equal(state.projectId, beforeClose.projectId);
  assert.equal(state.acceptedCount, 1);
  assert.equal(state.skippedCount, 1);
  assert.equal(state.view.navigationStep, 15);
  assert.equal(state.view.zoom, 1000);
  await page.waitForFunction(() => {
    const e = document.querySelector('.preview');
    return e?.scrollLeft === 120 && e?.scrollTop === 100;
  });
  assert.ok(
    Number(await page.locator('.preview').getAttribute('data-preview-cache')) <=
      7,
  );
  console.log('PASS: new process restored project and cached view.');
  await page.screenshot({ path: path.resolve('.tmp/ui-workspace.png') });
  const forbidden = await page.evaluate(async () => {
    try {
      await fetch('https://example.org');
      return false;
    } catch {
      return true;
    }
  });
  assert.equal(forbidden, true);
  assert.equal(
    await page.evaluate(() => window.open('https://example.org') === null),
    true,
  );
  await page.getByRole('button', { name: 'Zamknij projekt' }).click();
  await waitForHistory(page);
  await application.close();
  application = null;
  await rename(`${source} wybrane`, path.join(fixture, 'moved-output'));
  await launch();
  await continueFromHistory(page);
  await page.getByRole('button', { name: 'Wznów po naprawie' }).waitFor();
  assert.equal(
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)' })
      .isDisabled(),
    true,
  );
  await application.evaluate(
    ({ dialog }, directory) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [directory],
      });
    },
    path.join(fixture, 'moved-output'),
  );
  await page
    .getByRole('button', { name: 'Wskaż ponownie wynik', exact: true })
    .click();
  await imageReady();
  state = await snapshot();
  assert.equal(state.issue, null);
  assert.equal(state.acceptedCount, 1);
  await page.getByRole('button', { name: 'Zamknij projekt' }).click();
  await waitForHistory(page);
  const copiedProject = path.join(fixture, 'copied-project');
  const copiedOutput = path.join(fixture, 'copied-output');
  await cp(`${source} selekcja`, copiedProject, { recursive: true });
  await cp(path.join(fixture, 'moved-output'), copiedOutput, {
    recursive: true,
  });
  const originalOutput = await readFile(
    path.join(fixture, 'moved-output', 'manual-image-selection-output-v1.json'),
  );
  await application.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [directory],
    });
  }, copiedProject);
  await page
    .getByRole('button', { name: 'Otwórz projekt', exact: true })
    .click();
  await imageReady();
  assert.equal((await snapshot()).outputName, 'moved-output');
  await page
    .getByText('Inne lokalizacje źródła i wyniku', { exact: true })
    .click();
  await application.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [directory],
    });
  }, copiedOutput);
  await page
    .getByRole('button', { name: 'Wskaż ponownie wynik', exact: true })
    .click();
  await imageReady();
  assert.equal((await snapshot()).outputName, 'copied-output');
  assert.deepEqual(
    await readFile(
      path.join(
        fixture,
        'moved-output',
        'manual-image-selection-output-v1.json',
      ),
    ),
    originalOutput,
  );
  await page.getByRole('button', { name: 'Zmień zakres' }).click();
  await page.getByLabel('Początek zakresu', { exact: true }).fill('28');
  await page
    .getByRole('button', { name: 'Zapisz zakres', exact: true })
    .click();
  await settled();
  await bodyKey('f');
  await waitState((state) => state.selectionComplete);
  assert.equal((await snapshot()).acceptedCount, 2);
  await page
    .getByRole('button', { name: 'Restart partii', exact: true })
    .click();
  await page.getByRole('button', { name: 'Potwierdź restart partii' }).click();
  await waitState((state) => state.decisionCount === 0);
  assert.deepEqual(
    await readFile(
      path.join(
        fixture,
        'moved-output',
        'manual-image-selection-output-v1.json',
      ),
    ),
    originalOutput,
  );
  console.log(
    'PASS: packaged UI, JPEG, Enter/Tab, repeat/double-submit guards, undo, input safety, fullscreen, zoom/scroll/cache bounds, process reopen, recovery relink and cloned project explicit relink; original output unchanged.',
  );
} finally {
  await application?.close();
  await removeOwnedTemp(fixture, path.resolve('.tmp'));
}
