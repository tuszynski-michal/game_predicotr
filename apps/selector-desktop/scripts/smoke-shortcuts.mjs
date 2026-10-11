import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { removeOwnedTemp } from './release-support.mjs';
await mkdir('.tmp', { recursive: true });
const root = await mkdtemp(path.resolve('.tmp/shortcut-smoke-'));
const source = path.join(root, 'source');
const userData = path.join(root, 'user-data');
await mkdir(source);
await mkdir(userData);
const jpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAb/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=',
  'base64',
);
await writeFile(path.join(source, 'photo1.jpg'), jpeg);
await writeFile(path.join(source, 'photo2.jpg'), 'invalid JPEG');
let application;
const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
try {
  application = await electron.launch({
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  let page = await application.firstWindow();
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
  await page.getByRole('button', { name: 'Nowy projekt', exact: true }).click();
  await page.getByLabel('Pierwsza plansza', { exact: true }).fill('19');
  await page.getByLabel('Ostatnia plansza', { exact: true }).fill('20');
  await page.getByLabel('Kierunek numeracji').selectOption('descending');
  await page.getByRole('checkbox', { name: /Projekt i wynik będą/ }).check();
  await page
    .getByRole('button', { name: 'Wybierz zdjęcia i utwórz projekt' })
    .click();
  await page
    .getByRole('button', { name: 'Wybierz (Enter / F)' })
    .waitFor({ state: 'visible' });
  await page.waitForFunction(
    () =>
      ![...document.querySelectorAll('button')].find(
        (b) => b.textContent === 'Wybierz (Enter / F)',
      )?.disabled,
  );
  await page.getByLabel('Skok', { exact: true }).selectOption('20');
  await page.locator('h1').click();
  await page.keyboard.press('f');
  await page.getByTestId('counts').filter({ hasText: 'Wybrane: 1' }).waitFor();
  const result = await page.evaluate(() => window.selector.snapshot());
  const state = result.value;
  assert.equal(state.direction, 'descending');
  assert.equal(state.nextRangeStart, 10);
  assert.equal(
    state.source.images.findIndex((i) => i.id === state.currentImageId),
    1,
  );
  await page
    .getByText('Nie można odczytać JPEG-a.', { exact: false })
    .waitFor();
  assert.equal(
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)' })
      .isDisabled(),
    true,
  );
  const invalid = await page.evaluate(
    async (projectId) =>
      window.selector.execute({
        projectId,
        operationId: crypto.randomUUID(),
        command: { kind: 'accept', imagePath: '../../secret.jpg' },
      }),
    state.projectId,
  );
  assert.equal(invalid.ok, false);
  assert.equal(invalid.error.code, 'INVALID_ARGUMENT');
  await page.getByRole('button', { name: 'Poprzednie', exact: true }).click();
  await page.getByTestId('cursor').filter({ hasText: '1 / 2' }).waitFor();
  await page
    .getByText('To zdjęcie jest już wybrane.', { exact: false })
    .waitFor();
  assert.equal(
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)' })
      .isDisabled(),
    true,
  );
  const issue = await page.evaluate(() => window.selector.snapshot());
  assert.equal(issue.value.issue, null);
  assert.equal(issue.value.acceptedCount, 1);
  console.log(
    'PASS: descending F advances one despite step20, shortened range19–20, malformed JPEG blocks accept, repeat accept blocked, opaque IPC rejects paths.',
  );
  await page.getByRole('button', { name: 'Zamknij projekt' }).click();
  await page.getByRole('button', { name: /^Kontynuuj:/ }).waitFor();
  await application.close();
  application = null;
  const movedSource = path.join(root, 'moved-source');
  await rename(source, movedSource);
  application = await electron.launch({
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  page = await application.firstWindow();
  page.setDefaultTimeout(20000);
  await page.getByRole('button', { name: /^Kontynuuj:/ }).click();
  await page.getByRole('button', { name: 'Wznów po naprawie' }).waitFor();
  assert.equal(
    (await page.evaluate(() => window.selector.snapshot())).value.acceptedCount,
    1,
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
  }, movedSource);
  await page
    .getByRole('button', { name: 'Wskaż ponownie źródło', exact: true })
    .click();
  await page
    .getByText('To zdjęcie jest już wybrane.', { exact: false })
    .waitFor();
  const restored = await page.evaluate(() => window.selector.snapshot());
  assert.equal(restored.value.issue, null);
  assert.equal(restored.value.projectId, state.projectId);
  assert.equal(restored.value.acceptedCount, 1);
  assert.equal(restored.value.nextRangeStart, 10);
  console.log(
    'PASS: moved source recovered by explicit native relink after process restart; decisions and numbering preserved.',
  );
} finally {
  await application?.close();
  await removeOwnedTemp(root, path.resolve('.tmp'));
}
