import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';

const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
const fixture = path.resolve('.tmp/packaged-smoke');
await mkdir(fixture, { recursive: true });
// Valid 1x1 JPEG fixture. No production photographs are used.
await writeFile(
  path.join(fixture, 'photo1.jpg'),
  Buffer.from(
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAb/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=',
    'base64',
  ),
);
let application;
try {
  application = await electron.launch({
    executablePath,
    timeout: 20000,
    env: { ...process.env, ELECTRON_ENABLE_LOGGING: '1' },
  });
  const page = await application.firstWindow({ timeout: 20000 });
  await application.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [directory],
    });
  }, fixture);
  const external = [];
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) external.push(request.url());
  });
  await page.getByRole('button', { name: 'Wybierz katalog zdjęć' }).click();
  await page.waitForFunction(
    () => {
      const image = document.querySelector('img');
      return image?.complete && image.naturalWidth > 0;
    },
    null,
    { timeout: 15000 },
  );
  assert.deepEqual(
    await page
      .locator('img')
      .evaluate((image) => [image.naturalWidth, image.naturalHeight]),
    [1, 1],
  );
  assert.deepEqual(external, []);
  const blocked = await page.evaluate(async () => {
    try {
      await fetch('https://example.org');
      return false;
    } catch {
      return true;
    }
  });
  assert.equal(blocked, true);
  const popup = await page.evaluate(
    () => window.open('https://example.org') === null,
  );
  assert.equal(popup, true);
  await application.evaluate(({ dialog }) => {
    dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
  });
  await page.getByRole('button', { name: 'Wybierz katalog zdjęć' }).click();
  assert.equal(await page.locator('img').count(), 1);
  console.log(
    'PASS: packaged EXE, sandboxed bridge, local JPEG decoded, offline requests/windows blocked, picker cancel preserves preview.',
  );
} finally {
  await application?.close();
  await rm(fixture, { recursive: true, force: true });
}
