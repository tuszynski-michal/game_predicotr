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
const fixture = await mkdtemp(path.join(tempRoot, 'workflow-smoke-'));
const source = path.join(fixture, 'source');
const nextSource = path.join(fixture, 'next-source');
const userData = path.join(fixture, 'user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-workflow',
  fixture,
  tempRoot,
  userData: [userData],
});
let application, page;
async function choose(directory) {
  await application.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: directory === null,
      filePaths: directory ? [directory] : [],
    });
    dialog.showMessageBox = async () => {
      throw new Error('Unexpected confirmation');
    };
  }, directory);
}
async function launch(directory) {
  application = await smoke.launch(electron, {
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(10000);
  await choose(directory);
}
async function ready() {
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return (
      image?.complete &&
      image.naturalWidth > 0 &&
      document.querySelector('main')?.getAttribute('aria-busy') === 'false' &&
      [...document.querySelectorAll('button')].find(
        (button) => button.textContent.trim() === 'Zamknij projekt',
      )?.disabled === false
    );
  });
}
async function snapshot() {
  const result = await page.evaluate(() => window.selector.snapshot());
  assert.equal(result.ok, true);
  return result.value;
}
async function accept(count) {
  await ready();
  await page
    .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
    .click();
  await page.waitForFunction(
    (count) =>
      document
        .querySelector('[data-testid="counts"]')
        ?.textContent.includes(`Wybrane: ${count} ·`),
    count,
  );
  await ready();
}
try {
  await smoke.run(async () => {
    await Promise.all([mkdir(source), mkdir(nextSource)]);
    await launch(source);
    const jpeg = Buffer.from(
      await application.evaluate(({ nativeImage }) =>
        nativeImage
          .createFromBitmap(Buffer.alloc(1200 * 800 * 4, 160), {
            width: 1200,
            height: 800,
          })
          .toJPEG(80)
          .toString('base64'),
      ),
      'base64',
    );
    for (const directory of [source, nextSource])
      for (let index = 1; index <= 3; index++)
        await writeFile(path.join(directory, `photo${index}.jpg`), jpeg);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    assert.equal(await page.getByRole('checkbox').count(), 0);
    assert.equal(
      await page
        .getByRole('button', { name: 'Otwórz projekt', exact: true })
        .count(),
      0,
    );
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Mumie');
    if (await page.getByLabel('Aktualizacja', { exact: true }).count())
      await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
    await page.getByLabel('Pierwsza plansza', { exact: true }).fill('499996');
    await page
      .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
      .click();
    await ready();
    const initial = await snapshot();
    assert.equal(initial.sequenceUpperBound, 500000);
    assert.equal(
      await page
        .getByRole('button', { name: /Poprzednie|Następne|Otwórz logi/ })
        .count(),
      0,
    );
    const layout = await page.evaluate(() => {
      const actions = [
        ...document.querySelectorAll('.selection-actions button'),
      ];
      const headerControls = [
        ...document.querySelectorAll('header button, header select'),
      ];
      const primary = actions[0];
      const style = getComputedStyle(primary);
      const compact = {
        height: primary.getBoundingClientRect().height,
        background: style.backgroundColor,
        radius: style.borderRadius,
      };
      primary.style.setProperty('--button-height', 'initial');
      const defaultHeight = getComputedStyle(primary).minHeight;
      primary.style.removeProperty('--button-height');
      return {
        compact,
        defaultHeight,
        actionY: actions.map((b) => b.getBoundingClientRect().y),
        headerY: headerControls.map((b) => b.getBoundingClientRect().y),
        previewHeight: document
          .querySelector('.preview')
          .getBoundingClientRect().height,
      };
    });
    assert.equal(layout.compact.height, 32);
    assert.equal(layout.compact.background, 'rgb(112, 225, 180)');
    assert.equal(layout.compact.radius, '11px');
    assert.equal(layout.defaultHeight, '42px');
    assert.ok(Math.max(...layout.actionY) - Math.min(...layout.actionY) < 1);
    assert.ok(Math.max(...layout.headerY) - Math.min(...layout.headerY) < 3);
    assert.ok(layout.previewHeight > 400);
    await accept(1);
    const manifest = JSON.parse(
      await readFile(
        path.join(
          fixture,
          'Mumie a1 499996-500000',
          'manual-image-selection-output-v1.json',
        ),
        'utf8',
      ),
    );
    assert.equal(manifest.decisions[0].outputName, 'seq_499996-500000.jpg');
    assert.equal(manifest.decisions[0].activeBoardCount, 5);
    assert.equal(manifest.selectionComplete, true);
    await page.getByRole('button', { name: 'Zakres', exact: true }).click();
    await page.getByLabel('Początek zakresu', { exact: true }).fill('499987');
    await page
      .getByLabel('Kierunek numeracji', { exact: true })
      .selectOption('descending');
    await page.getByRole('button', { name: 'Zapisz', exact: true }).click();
    await ready();
    await accept(2);
    assert.equal((await snapshot()).nextRangeStart, 499978);
    await page.getByLabel('Skok', { exact: true }).selectOption('5');
    await page.getByLabel('Zoom', { exact: true }).selectOption('150');
    await page
      .getByRole('button', { name: 'Pełny ekran (F11)', exact: true })
      .click();
    await page
      .getByRole('button', { name: 'Wyjdź (F11)', exact: true })
      .waitFor();
    assert.equal(
      await page
        .getByRole('button', { name: 'Wybierz kolejny folder', exact: true })
        .isVisible(),
      false,
    );
    await page.keyboard.press('Escape');
    await page
      .getByRole('button', { name: 'Pełny ekran (F11)', exact: true })
      .waitFor();
    const version = await application.evaluate(({ app }) => app.getVersion());
    const evidence = path.resolve('../../artifacts/selector-releases', version);
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, 'selection.png') });
    await choose(null);
    await page
      .getByRole('button', { name: 'Wybierz kolejny folder', exact: true })
      .click();
    await ready();
    assert.equal((await snapshot()).projectId, initial.projectId);
    await choose(nextSource);
    await page
      .getByRole('button', { name: 'Wybierz kolejny folder', exact: true })
      .click();
    assert.equal(
      await page.getByLabel('Nazwa gry', { exact: true }).inputValue(),
      'Mumie',
    );
    assert.equal(
      await page.getByLabel('Pierwsza plansza', { exact: true }).inputValue(),
      '',
    );
    assert.equal(
      await page.getByLabel('Kierunek numeracji', { exact: true }).inputValue(),
      'descending',
    );
    await page.getByRole('button', { name: 'Anuluj', exact: true }).click();
    await ready();
    assert.equal((await snapshot()).acceptedCount, 2);
    await page
      .getByRole('button', { name: 'Wybierz kolejny folder', exact: true })
      .click();
    await page.getByLabel('Pierwsza plansza', { exact: true }).fill('100');
    await page
      .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
      .click();
    await ready();
    await accept(1);
    const next = await snapshot();
    assert.notEqual(next.projectId, initial.projectId);
    assert.equal(next.nextRangeStart, 91);
    await smoke.close(application);
    application = null;
    await launch(nextSource);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await ready();
    const resumed = await snapshot();
    assert.equal(resumed.projectId, next.projectId);
    assert.equal(resumed.direction, 'descending');
    assert.equal(resumed.nextRangeStart, 91);
    assert.equal(resumed.gameName, 'Mumie');
    console.log(
      'PASS: shared button style/defaults, compact rows, 500000 filename/manifest, range direction, fullscreen, next-folder cancellation and new-process resume.',
    );
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
