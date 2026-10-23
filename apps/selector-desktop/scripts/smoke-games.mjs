import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createOwnedSmoke } from './release-support.mjs';

const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const fixture = await mkdtemp(path.join(tempRoot, 'games-smoke-'));
const source = path.join(fixture, 'source');
const userData = path.join(fixture, 'user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-games',
  fixture,
  tempRoot,
  userData: [userData],
});
let application, page;
async function launch() {
  application = await smoke.launch(electron, {
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(10000);
  await application.evaluate(({ dialog }, source) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [source],
    });
    dialog.showMessageBox = async () => {
      throw new Error('Unexpected confirmation');
    };
  }, source);
}
async function begin() {
  await page
    .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
    .click();
  await page.getByLabel('Nazwa gry', { exact: true }).waitFor();
}
try {
  await smoke.run(async () => {
    await mkdir(source);
    await launch();
    const jpeg = await application.evaluate(({ nativeImage }) =>
      nativeImage
        .createFromBitmap(Buffer.alloc(400 * 300 * 4, 160), {
          width: 400,
          height: 300,
        })
        .toJPEG(80)
        .toString('base64'),
    );
    await writeFile(
      path.join(source, 'photo.jpg'),
      Buffer.from(jpeg, 'base64'),
    );
    await begin();
    const game = page.getByLabel('Nazwa gry', { exact: true });
    await game.fill('777');
    await game.press('Enter');
    await page.waitForFunction(async () =>
      (await window.selector.games()).value?.includes('777'),
    );
    assert.equal(
      (await page.evaluate(() => window.selector.snapshot())).value,
      null,
    );
    await smoke.close(application);
    await launch();
    await begin();
    await page.getByLabel('Nazwa gry', { exact: true }).press('Escape');
    await page.getByRole('button', { name: 'Pokaż gry', exact: true }).click();
    await page.getByRole('option', { name: '777', exact: true }).click();
    assert.equal(
      await page.getByLabel('Nazwa gry', { exact: true }).inputValue(),
      '777',
    );
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Mumie');
    await page.getByLabel('Nazwa gry', { exact: true }).press('Enter');
    await page.waitForFunction(
      async () => (await window.selector.games()).value?.length === 2,
    );
    await page.getByLabel('Nazwa gry', { exact: true }).fill('77');
    await page.getByRole('option', { name: '777', exact: true }).waitFor();
    assert.equal(
      await page.getByRole('option', { name: 'Mumie', exact: true }).count(),
      0,
    );
    await page.getByRole('option', { name: '777', exact: true }).click();
    const update = page.getByLabel('Aktualizacja', { exact: true });
    for (const invalid of ['a', 'x_a1', 'z_a1x', 'a1 ']) {
      await update.fill(invalid);
      await page
        .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
        .click();
      assert.equal(
        await update.evaluate((input) => input.validity.valid),
        false,
      );
      assert.equal(
        (await page.evaluate(() => window.selector.snapshot())).value,
        null,
      );
    }
    await update.fill('z_a003');
    const evidence = path.resolve('../../artifacts/selector-releases/1.0.2');
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: path.join(evidence, 'games-update-form.png'),
    });
    await page
      .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
      .click();
    await page.waitForFunction(
      async () =>
        (await window.selector.snapshot()).value?.gameUpdate === 'z_a003',
    );
    await page.waitForFunction(
      () =>
        document.querySelector('.preview img')?.naturalWidth > 0 &&
        document.querySelector('main')?.getAttribute('aria-busy') === 'false',
    );
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
      .click();
    await page.waitForFunction(
      async () => (await window.selector.snapshot()).value?.acceptedCount === 1,
    );
    await page.waitForFunction(
      () =>
        document.querySelector('main')?.getAttribute('aria-busy') === 'false',
    );
    const manifest = JSON.parse(
      await readFile(
        path.join(`${source} wybrane`, 'manual-image-selection-output-v1.json'),
        'utf8',
      ),
    );
    assert.equal(manifest.gameUpdate, undefined);
    assert.equal(manifest.decisions[0].outputName, 'seq_1-9.jpg');
    await smoke.close(application);
    await launch();
    await page.getByLabel('Ostatnie projekty', { exact: true }).waitFor();
    await page
      .getByRole('option', { name: '777 z_a003 — source', exact: true })
      .waitFor({ state: 'attached' });
    await page.screenshot({
      path: path.join(evidence, 'games-update-history.png'),
    });
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page.waitForFunction(
      async () =>
        (await window.selector.snapshot()).value?.gameUpdate === 'z_a003',
    );
    await page.waitForFunction(
      () =>
        document.querySelector('main')?.getAttribute('aria-busy') === 'false',
    );
    assert.equal(
      (await page.evaluate(() => window.selector.snapshot())).value
        .acceptedCount,
      1,
    );
    console.log(
      'PASS: Enter adds without submitting, catalog survives restart, dropdown filters/selects, update validation, unchanged export names and new-process history/resume.',
    );
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
