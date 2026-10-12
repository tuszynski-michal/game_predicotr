import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { createOwnedSmoke } from './release-support.mjs';
import { waitForHistory } from './ui-smoke-support.mjs';

const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
const base = path.resolve('.tmp');
await mkdir(base, { recursive: true });
const root = await mkdtemp(path.join(base, 'start-smoke-'));
const userData = path.join(root, 'user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-start',
  fixture: root,
  tempRoot: path.resolve('.tmp'),
  userData: [userData],
});
let application;
let page;
const metadataPath = process.argv
  .find((arg) => arg.startsWith('--release-metadata='))
  ?.slice('--release-metadata='.length);
let provenance;
async function launch(source) {
  application = await smoke.launch(electron, {
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(20000);
  if (process.argv.includes('--diagnostic-fault-after-start')) {
    const log = await readFile(
      path.join(userData, 'logs', 'selector.log'),
      'utf8',
    );
    assert.match(log, /application-start/);
    throw new Error('Controlled diagnostic failure after application start');
  }
  await application.evaluate(({ dialog }, source) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [source],
    });
    dialog.showMessageBox = async () => {
      throw new Error('Unexpected extra confirmation');
    };
  }, source);
  if (provenance) {
    const built = await application.evaluate(({ app }) => ({
      version: app.getVersion(),
      info: JSON.parse(
        process
          .getBuiltinModule('fs')
          .readFileSync(`${app.getAppPath()}/dist/build-info.json`, 'utf8'),
      ),
    }));
    assert.equal(built.version, provenance.applicationVersion);
    assert.equal(built.info.sourceCommit, provenance.sourceCommit);
    assert.equal(built.info.dirty, provenance.dirty);
  }
}
async function state() {
  const result = await page.evaluate(() => window.selector.snapshot());
  assert.equal(result.ok, true);
  return result.value;
}
async function imageReady() {
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return image?.complete && image.naturalWidth > 0;
  });
  await page.waitForFunction(
    () =>
      !document.querySelector('.save-state')?.textContent?.includes('w toku'),
  );
}
try {
  await smoke.run(async () => {
    await mkdir(userData);
    provenance = metadataPath
      ? JSON.parse(await readFile(metadataPath, 'utf8'))
      : null;

    for (const [direction, batch, game] of [
      ['ascending', '123', 'Mumie'],
      ['descending', '456', 'Siódemki'],
    ]) {
      const source = path.join(root, 'Mumie', batch);
      await mkdir(source, { recursive: true });
      await launch(source);
      const jpeg = await application.evaluate(({ nativeImage }) =>
        nativeImage
          .createFromBitmap(Buffer.alloc(400 * 300 * 4, 170), {
            width: 400,
            height: 300,
          })
          .toJPEG(80)
          .toString('base64'),
      );
      for (let i = 1; i <= 3; i++)
        await writeFile(
          path.join(source, `photo${i}.jpg`),
          Buffer.from(jpeg, 'base64'),
        );
      await page
        .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
        .click();
      await page.getByLabel('Nazwa gry', { exact: true }).fill(game);
      await page.getByLabel('Pierwsza plansza', { exact: true }).fill('20');
      await page
        .getByLabel('Kierunek numeracji', { exact: true })
        .selectOption(direction);
      await page
        .getByRole('checkbox', { name: /Projekt i wynik będą/ })
        .check();
      assert.equal(
        await page.getByRole('checkbox', { name: /Wybiorę osobne/ }).count(),
        0,
      );
      if (direction === 'ascending')
        await page.screenshot({
          path: path.resolve('.tmp/selector-new-project.png'),
        });
      await page
        .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
        .click();
      await imageReady();
      const initial = await state();
      assert.equal(initial.gameName, game);
      assert.equal(initial.direction, direction);
      await page.locator('h1').click();
      await page.keyboard.press('Enter');
      await page.waitForFunction(
        async () =>
          (await window.selector.snapshot()).value?.acceptedCount === 1,
      );
      await imageReady();
      const saved = await state();
      const savedPath = saved.source.images.find(
        (i) => i.id === saved.currentImageId,
      ).relativePath;
      assert.equal(savedPath, 'photo2.jpg');
      assert.equal(saved.nextRangeStart, direction === 'ascending' ? 29 : 11);
      assert.deepEqual(
        await readFile(path.join(`${source} wybrane`, 'seq_20-28.jpg')),
        Buffer.from(jpeg, 'base64'),
      );
      await smoke.close(application);
      application = null;
      await launch(source);
      await waitForHistory(page);
      const history = page.getByLabel('Ostatnie projekty', { exact: true });
      assert.ok(
        (await history.locator('option').allTextContents()).includes(
          `${game} — ${batch}`,
        ),
      );
      if (direction === 'descending')
        await page.screenshot({
          path: path.resolve('.tmp/selector-history.png'),
        });
      await page
        .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
        .click();
      await imageReady();
      const resumed = await state();
      assert.equal(resumed.projectId, initial.projectId);
      assert.equal(resumed.nextRangeStart, saved.nextRangeStart);
      assert.equal(resumed.direction, direction);
      assert.equal(resumed.gameName, game);
      assert.equal(resumed.acceptedCount, 1);
      assert.equal(
        resumed.source.images.find((i) => i.id === resumed.currentImageId)
          .relativePath,
        savedPath,
      );
      assert.equal(await page.getByLabel('Nazwa gry').count(), 0);
      await page
        .getByRole('button', { name: 'Zamknij projekt', exact: true })
        .click();
      await waitForHistory(page);
      await page
        .getByLabel('Ostatnie projekty', { exact: true })
        .selectOption(initial.projectId);
      await page
        .getByRole('button', { name: 'Kontynuuj', exact: true })
        .click();
      await imageReady();
      assert.equal((await state()).projectId, initial.projectId);
      if (direction === 'descending') {
        const moved = path.join(root, 'Mumie', 'moved-456');
        await rename(source, moved);
        await application.evaluate(({ dialog }, moved) => {
          dialog.showOpenDialog = async () => ({
            canceled: false,
            filePaths: [moved],
          });
          dialog.showMessageBox = async () => ({
            response: 1,
            checkboxChecked: false,
          });
        }, moved);
        await page
          .getByText('Inne lokalizacje źródła i wyniku', { exact: true })
          .click();
        await page
          .getByRole('button', { name: 'Wskaż ponownie źródło', exact: true })
          .click();
        await imageReady();
        assert.equal((await state()).projectId, initial.projectId);
        await smoke.close(application);
        application = null;
        await launch(moved);
        await page
          .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
          .click();
        await imageReady();
        assert.equal((await state()).projectId, initial.projectId);
        assert.equal((await state()).nextRangeStart, saved.nextRangeStart);
        console.log(
          'PASS: moved source relink updates history; source reselect resumes the same project after another process restart.',
        );
      }
      console.log(
        `PASS: ${direction} one-folder start, game history dropdown and source reselect resume after new process.`,
      );
      await smoke.close(application);
      application = null;
    }
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
