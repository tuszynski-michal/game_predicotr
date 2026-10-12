import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { removeOwnedTemp } from './release-support.mjs';
const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
await mkdir('.tmp', { recursive: true });
const fixture = await mkdtemp(path.resolve('.tmp/ux-smoke-'));
const source = path.join(fixture, 'source');
const userData = path.join(fixture, 'user-data');
await mkdir(source);
await mkdir(userData);
let application;
let page;
async function launch() {
  application = await electron.launch({
    executablePath,
    args: [`--user-data-dir=${userData}`],
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
async function ready() {
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return image?.complete && image.naturalWidth > 0;
  });
  await page.waitForFunction(
    () =>
      !document.querySelector('.save-state')?.textContent.includes('w toku'),
  );
}
try {
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
  for (let i = 1; i <= 3; i++)
    await writeFile(path.join(source, `photo${i}.jpg`), jpeg);
  await page.getByRole('button', { name: 'Nowy projekt', exact: true }).click();
  await page.getByRole('checkbox', { name: /Projekt i wynik będą/ }).check();
  await page
    .getByRole('button', { name: 'Wybierz zdjęcia i utwórz projekt' })
    .click();
  await ready();
  await page.getByRole('button', { name: 'Następne', exact: true }).click();
  await page.getByText('Pozycja zdjęcia zapisana.', { exact: true }).waitFor();
  await ready();
  assert.equal(
    (await page.evaluate(() => window.selector.snapshot())).value.acceptedCount,
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
  await page.getByTestId('counts').filter({ hasText: 'Wybrane: 1' }).waitFor();
  await ready();
  const current = (await page.evaluate(() => window.selector.snapshot())).value;
  assert.equal(current.view.scrollX, finalScroll.scrollX);
  assert.equal(current.view.scrollY, finalScroll.scrollY);
  await page.getByRole('button', { name: 'Zamknij projekt' }).click();
  await page.getByRole('button', { name: /^Kontynuuj:/ }).waitFor();
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
    .getByRole('button', { name: 'Otwórz projekt', exact: true })
    .click();
  await page
    .getByText('Weryfikacja źródła i sum kontrolnych JPEG-ów…', { exact: true })
    .waitFor();
  await ready();
  await application.close();
  application = null;
  await launch();
  await page.getByRole('button', { name: /^Kontynuuj:/ }).click();
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
    'PASS: removed picker, open verification, NAV message, scroll burst with accept, project-close flush and new-process view/decisions.',
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
} finally {
  await application?.close();
  await removeOwnedTemp(fixture, path.resolve('.tmp'));
}
