import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
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
try {
  application = await electron.launch({
    executablePath: path.resolve(
      process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
    ),
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  const page = await application.firstWindow();
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
} finally {
  await application?.close();
  await rm(root, { recursive: true, force: true });
}
