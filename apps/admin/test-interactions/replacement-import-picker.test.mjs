import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { mkdir, mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve, sep } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { DiskDirectory } from '../test/fixtures/replacement-disk-directory.mjs';
import {
  createReplacementRepair,
  replacementCanonicalJson,
  replacementRequestPayload,
} from '../../../packages/manual-image-selection-core/src/replacement-repair.ts';
import { ReplacementImportPicker } from '../src/features/imports/replacement-import-picker.tsx';
import { ReplacementStartRecovery } from '../src/features/imports/replacement-start-recovery.tsx';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const name of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
globalThis.React = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
after(() => dom.window.close());
const click = (node) =>
  act(async () => {
    node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent === text,
  );

test('picker selects only committed A from request A+B and resumes same upload after reload without rewriting local output', async (t) => {
  localStorage.clear();
  const artifacts = fileURLToPath(
    new URL('../../../artifacts/task1131/ui/', import.meta.url),
  );
  await mkdir(artifacts, { recursive: true });
  const directory = await mkdtemp(join(artifacts, 'picker-'));
  t.after(async () => {
    assert.ok(resolve(directory).startsWith(resolve(artifacts) + sep));
    await rm(directory, { recursive: true, force: true });
  });
  const fixture = JSON.parse(
    await readFile(
      new URL(
        '../../../packages/admin-api-client/test/fixtures/source-replacement-request-v1.json',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  const second = randomUUID();
  fixture.entries.push({
    ...fixture.entries[0],
    entryId: second,
    sequenceNumbers: [10, 11, 12, 13, 14, 15, 16, 17, 18],
  });
  fixture.allowedRanges.push({
    entryId: second,
    sequenceStart: 10,
    sequenceEnd: 18,
  });
  fixture.digest = createHash('sha256')
    .update(replacementCanonicalJson(replacementRequestPayload(fixture)))
    .digest('hex');
  const jpeg = Buffer.from([255, 216, 255, 217]);
  const checksum = createHash('sha256').update(jpeg).digest('hex');
  const handle = new DiskDirectory(directory, undefined, true);
  const manifest = {
    ...createReplacementRepair(
      fixture,
      'repair',
      handle.name,
      '2026-11-03T00:00:00Z',
    ),
    revision: 1,
    journal: [
      {
        id: randomUUID(),
        entryId: fixture.entries[0].entryId,
        fileName: 'seq_1-9.jpg',
        checksumSha256: checksum,
        size: jpeg.length,
        sourcePath: 'source.jpg',
        sourceIndex: null,
        occurredAt: '2026-11-03T00:00:00Z',
        state: 'committed',
      },
    ],
  };
  const path = join(directory, 'manual-image-selection-repair-v3.json');
  await writeFile(path, JSON.stringify(manifest));
  await writeFile(join(directory, 'seq_1-9.jpg'), jpeg);
  const before = await readFile(path);
  window.showDirectoryPicker = async () => handle;
  const creates = [],
    ready = [];
  let finalizeCount = 0;
  const api = {
    planBrowserImageSelectionUpload: async () => {
      throw new Error('canonical skip forbidden');
    },
    createBrowserImageSelection: async (body) => {
      creates.push(body);
      return { data: { uploadId: 'ready-upload' } };
    },
    uploadBrowserImageSelectionFile: async (id, index, name, file) => {
      assert.equal(name, 'seq_1-9.jpg');
      assert.deepEqual(Buffer.from(await file.arrayBuffer()), jpeg);
      return { data: { uploadedFileCount: 1, expectedFileCount: 1 } };
    },
    finalizeBrowserImageSelection: async () => {
      if (!finalizeCount++) throw new Error('lost response');
      return { data: { supportedFileCount: 1 } };
    },
    cancelBrowserImageSelection: async () => {
      throw new Error('must preserve retry');
    },
  };
  const render = async () => {
    const root = createRoot(document.getElementById('root'));
    await act(async () =>
      root.render(
        React.createElement(ReplacementImportPicker, {
          api,
          gameId: fixture.gameId,
          gameLabel: 'Gra testowa',
          disabled: false,
          onReady: async (id) => ready.push(id),
        }),
      ),
    );
    return root;
  };
  let root = await render();
  await click(button('Otwórz gotowe zamienniki'));
  assert.equal(document.querySelectorAll('input[type=checkbox]').length, 1);
  assert.equal(button('Prześlij wybrane zamienniki').disabled, true);
  await click(document.querySelector('input[type=checkbox]'));
  await click(button('Prześlij wybrane zamienniki'));
  assert.equal(ready.length, 0);
  assert.match(document.body.textContent, /ponów przesyłanie/);
  await act(async () => root.unmount());
  root = await render();
  await click(button('Otwórz gotowe zamienniki'));
  await click(document.querySelector('input[type=checkbox]'));
  await click(button('Prześlij wybrane zamienniki'));
  assert.deepEqual(ready, ['ready-upload']);
  assert.deepEqual(creates[0], creates[1]);
  assert.equal(creates[0].replacementSelection.request.entries.length, 2);
  assert.deepEqual(creates[0].replacementSelection.selectedEntryIds, [
    fixture.entries[0].entryId,
  ]);
  assert.equal(creates[0].replacementSelection.files.length, 1);
  assert.deepEqual(await readFile(path), before);
  assert.equal(handle.writes, 0);
  await act(async () => root.unmount());
});

test('pending start receipt is recoverable without staging or a fresh preflight after reload', async () => {
  localStorage.clear();
  const body = {
    gameId: 'game',
    manifestChecksumSha256: 'manifest',
    preflightChecksumSha256: 'original-report',
    replacementSelection: {
      request: { gameId: 'game' },
      files: [{ rangeStart: 101, rangeEnd: 102 }],
    },
  };
  localStorage.setItem('replacement-start:game:upload', JSON.stringify(body));
  const sent = [];
  const recovered = [];
  const api = {
    startReadyBrowserImageImport: async (upload, command) => {
      sent.push([upload, command]);
      if (sent.length === 1) throw new Error('lost response');
      return {
        data: { created: false, job: { id: 'saved-job' }, preflight: {} },
      };
    },
  };
  const render = async () => {
    const root = createRoot(document.getElementById('root'));
    await act(async () =>
      root.render(
        React.createElement(ReplacementStartRecovery, {
          api,
          gameId: 'game',
          disabled: false,
          refreshKey: null,
          onRecovered: async (value) => recovered.push(value.job.id),
        }),
      ),
    );
    return root;
  };
  let root = await render();
  await click(button('Odtwórz potwierdzenie: plansze 101–102'));
  assert.equal(recovered.length, 0);
  await act(async () => root.unmount());
  root = await render();
  await click(button('Odtwórz potwierdzenie: plansze 101–102'));
  assert.deepEqual(sent, [
    ['upload', body],
    ['upload', body],
  ]);
  assert.deepEqual(recovered, ['saved-job']);
  assert.equal(localStorage.getItem('replacement-start:game:upload'), null);
  await act(async () => root.unmount());
});
