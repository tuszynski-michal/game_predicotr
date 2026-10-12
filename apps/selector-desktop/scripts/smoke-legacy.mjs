import { continueFromHistory } from './ui-smoke-support.mjs';
import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  writeFile,
  readFile,
  readdir,
  stat,
  utimes,
} from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { buildRemoteSourceManifestV1 } from '@game-predictor/manual-image-selection-core';
import { removeOwnedTemp } from './release-support.mjs';
const executablePath = path.resolve(
  process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
);
await mkdir('.tmp', { recursive: true });
const fixture = await mkdtemp(path.resolve('.tmp/ui-legacy-'));
const source = path.join(fixture, 'source'),
  oldOutput = path.join(fixture, 'old-output'),
  newProject = path.join(fixture, 'new-project'),
  newOutput = path.join(fixture, 'new-output'),
  userData = path.join(fixture, 'user-data');
for (const directory of [source, oldOutput, newProject, newOutput, userData])
  await mkdir(directory);
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
let application, page;
async function launch(directories) {
  application = await electron.launch({
    executablePath,
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  assert.equal(
    await application.evaluate(({ app }) => app.getPath('userData')),
    userData,
  );
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(20000);
  await application.evaluate(({ dialog }, chosen) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [chosen.shift()],
    });
    dialog.showMessageBox = async () => ({
      response: 1,
      checkboxChecked: false,
    });
  }, directories);
}
async function originals() {
  const result = [];
  for (const root of [source, oldOutput])
    for (const name of (await readdir(root)).sort()) {
      const file = path.join(root, name),
        details = await stat(file);
      result.push([
        file,
        hash(await readFile(file)),
        details.mtimeMs,
        details.size,
      ]);
    }
  return result;
}
try {
  await launch([source, oldOutput, source, oldOutput, newProject, newOutput]);
  const jpeg = Buffer.from(
    await application.evaluate(({ nativeImage }) =>
      nativeImage
        .createFromBitmap(Buffer.alloc(800 * 600 * 4, 165), {
          width: 800,
          height: 600,
        })
        .toJPEG(80)
        .toString('base64'),
    ),
    'base64',
  );
  const inventory = [];
  for (const name of ['photo1.jpg', 'photo2.jpg', 'photo10.jpg']) {
    const file = path.join(source, name);
    await writeFile(file, jpeg);
    await utimes(file, 1700000000, 1700000000.123);
    const info = await stat(file);
    inventory.push({
      relativePath: name,
      name,
      sizeBytes: info.size,
      lastModifiedMs: Math.trunc(info.mtimeMs),
      mimeType: 'image/jpeg',
    });
  }
  const sourceManifest = await buildRemoteSourceManifestV1(
    inventory,
    'directory_handle',
  );
  const manifest = {
    schemaVersion: 2,
    storageMode: 'operator_local',
    sessionId: 'original-session',
    batchId: 'original-batch',
    sourceDirectoryName: 'source',
    sourceManifestChecksumSha256: sourceManifest.manifestChecksumSha256,
    fileCount: 3,
    firstLayout: 19,
    direction: 'descending',
    sequenceUpperBound: null,
    selectionComplete: false,
    decisions: [
      {
        action: 'accepted',
        operationId: 'old-accepted',
        fileId: 'browser-image',
        sourceIndex: 0,
        imagePath: 'photo1.jpg',
        imageChecksumSha256: hash(jpeg),
        outputName: 'seq_19-27.jpg',
        rangeStart: 19,
        rangeEnd: 27,
        selectionGeneration: 4,
        activeBoardCount: 9,
      },
      {
        action: 'skipped',
        operationId: 'old-skipped',
        fileId: null,
        sourceIndex: 2,
        imagePath: null,
        imageChecksumSha256: null,
        outputName: null,
        rangeStart: 10,
        rangeEnd: 18,
        selectionGeneration: 4,
        activeBoardCount: 9,
      },
    ],
    currentIndex: 2,
    nextRangeStart: 1,
    updatedAt: '2026-10-11T00:00:00.000Z',
  };
  await writeFile(path.join(oldOutput, 'seq_19-27.jpg'), jpeg);
  await writeFile(
    path.join(oldOutput, 'manual-image-selection-output-v1.json'),
    JSON.stringify(manifest),
  );
  const original = await originals();
  await page
    .getByRole('button', { name: 'Przejmij sesję Reviewera', exact: true })
    .click();
  await page
    .getByRole('heading', { name: 'Podgląd sesji Reviewera' })
    .waitFor();
  assert.match(
    await page.locator('.legacy-preview').textContent(),
    /Aktualne zdjęcie: 2/,
  );
  assert.match(
    await page.locator('.legacy-preview').textContent(),
    /Wybrane: 1/,
  );
  await page.screenshot({ path: path.resolve('.tmp/ui-legacy-preview.png') });
  assert.equal(
    (await page.evaluate(() => window.selector.legacyAdopt('../arbitrary'))).ok,
    false,
  );
  await page
    .getByRole('button', { name: 'Anuluj przejęcie', exact: true })
    .click();
  assert.deepEqual(await originals(), original);
  assert.deepEqual(await readdir(newProject), []);
  assert.deepEqual(await readdir(newOutput), []);
  await page
    .getByRole('button', { name: 'Przejmij sesję Reviewera', exact: true })
    .click();
  await page
    .getByRole('heading', { name: 'Podgląd sesji Reviewera' })
    .waitFor();
  await page
    .getByRole('button', {
      name: 'Utwórz nowy projekt z tej sesji',
      exact: true,
    })
    .click();
  await page.waitForFunction(() =>
    document
      .querySelector('[data-testid="counts"]')
      ?.textContent.includes('Wybrane: 1'),
  );
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return image?.complete && image.naturalWidth === 800;
  });
  const response = await page.evaluate(() => window.selector.snapshot());
  assert.equal(response.ok, true);
  const state = response.value;
  assert.equal(state.skippedCount, 1);
  assert.equal(state.nextRangeStart, 1);
  assert.equal(
    state.source.images.findIndex((i) => i.id === state.currentImageId),
    1,
  );
  assert.deepEqual(await originals(), original);
  const imported = JSON.parse(
    await readFile(
      path.join(newOutput, 'manual-image-selection-output-v1.json'),
      'utf8',
    ),
  );
  assert.deepEqual(imported.decisions, manifest.decisions);
  assert.equal(imported.currentIndex, 1);
  assert.equal(imported.sourceTraversalSemantics, 'natural_v2');
  assert.notEqual(imported.sessionId, manifest.sessionId);
  await application.close();
  application = null;
  await launch([]);
  await continueFromHistory(page);
  await page.waitForFunction(() =>
    document
      .querySelector('[data-testid="counts"]')
      ?.textContent.includes('Wybrane: 1'),
  );
  const reopened = await page.evaluate(() => window.selector.snapshot());
  assert.equal(reopened.value.projectId, state.projectId);
  assert.equal(reopened.value.skippedCount, 1);
  assert.equal(reopened.value.nextRangeStart, 1);
  assert.deepEqual(await originals(), original);
  console.log(
    'PASS: actual packaged EXE legacy preview, cancellation, opaque-token rejection, confirmed adoption, original bytes/metadata and new-process continuation.',
  );
} finally {
  await application?.close();
  await removeOwnedTemp(fixture, path.resolve('.tmp'));
}
