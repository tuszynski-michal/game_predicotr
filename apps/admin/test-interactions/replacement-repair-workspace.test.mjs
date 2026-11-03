import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { readFile } from 'node:fs/promises';
import { ReplacementRepairWorkspace } from '../src/features/manual-image-selection/replacement-repair-workspace.tsx';

const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();
const fixture = JSON.parse(
  await readFile(
    new URL(
      '../../../packages/admin-api-client/test/fixtures/source-replacement-request-v1.json',
      import.meta.url,
    ),
  ),
);

async function mount(t, getGame) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
  const old = {
    React: globalThis.React,
    window: globalThis.window,
    document: globalThis.document,
    Image: globalThis.Image,
    IS_REACT_ACT_ENVIRONMENT: globalThis.IS_REACT_ACT_ENVIRONMENT,
  };
  Object.assign(globalThis, {
    React,
    window: dom.window,
    document: dom.window.document,
    Image: dom.window.Image,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ReplacementRepairWorkspace, {
        apiBaseUrl: 'http://configured.invalid',
        client: {
          getGame,
          getSourceReplacementBatch: async () => {
            throw new Error('no write authorized');
          },
        },
      }),
    ),
  );
  t.after(async () => {
    await act(async () => root.unmount());
    dom.window.close();
    Object.assign(globalThis, old);
  });
  return dom;
}
async function upload(dom, request) {
  const field = document.querySelector('input[type=file]');
  Object.defineProperty(field, 'files', {
    configurable: true,
    value: [new File([JSON.stringify(request)], 'request.json')],
  });
  await act(async () => {
    field.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    await new Promise((done) => setTimeout(done, 30));
  });
}

test('global repair identifies the current API game and exact ranges; duplicate candidates have no automatic choice', async (t) => {
  const calls = [];
  const dom = await mount(t, async (id) => {
    calls.push(id);
    return { data: { id, name: '777 a2', code: '777a2' } };
  });
  await upload(dom, { ...fixture, origin: 'https://untrusted.invalid' });
  assert.deepEqual(calls, [fixture.gameId]);
  assert.match(document.body.textContent, /Gra: 777 a2 \(777a2\)/);
  assert.match(document.body.textContent, /1–9/);
  assert.match(document.body.textContent, /Backendowa luka pozostaje otwarta/);
  const readonly = [];
  dom.window.showDirectoryPicker = async (options) => {
    readonly.push(options.mode);
    return {
      name: 'nowe-zdjecia',
      async *entries() {
        for (const name of ['seq_1-9.jpg', 'seq_1-9.jpeg'])
          yield [
            name,
            {
              kind: 'file',
              name,
              getFile: async () => {
                throw new Error('listing must not read image bytes');
              },
            },
          ];
      },
    };
  };
  const button = [...document.querySelectorAll('button')].find((row) =>
    row.textContent.includes('Wybierz nowe zdjęcia'),
  );
  await act(async () => button.click());
  assert.deepEqual(readonly, ['read']);
  const selects = document.querySelectorAll('select');
  assert.equal(selects[1].options.length, 3);
  assert.equal(selects[1].value, '');
  assert.equal(
    [...document.querySelectorAll('button')].find(
      (row) => row.textContent === 'Przygotuj wybrane zdjęcie',
    ).disabled,
    true,
  );
});

test('unavailable current game fails visibly before exposing source/output controls', async (t) => {
  const dom = await mount(t, async () => ({ error: { message: 'offline' } }));
  await upload(dom, fixture);
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /Nie można potwierdzić gry/,
  );
  assert.equal(document.querySelectorAll('select').length, 0);
});

test('switching a duplicate to a slow source keeps save blocked until the new image decodes and waits 300ms', async (t) => {
  const dom = await mount(t, async (id) => ({
    data: { id, name: '777 a2', code: '777a2' },
  }));
  globalThis.Image = class {
    async decode() {}
  };
  await upload(dom, fixture);
  let release;
  const delayed = new Promise((done) => {
    release = done;
  });
  const sourceDirectory = {
    name: 'new',
    async *entries() {
      yield [
        'seq_1-9.jpg',
        {
          kind: 'file',
          getFile: async () => new File(['first'], 'seq_1-9.jpg'),
        },
      ];
      yield ['seq_1-9.jpeg', { kind: 'file', getFile: () => delayed }];
    },
    isSameEntry: async () => false,
    resolve: async () => null,
  };
  const output = {
    name: 'output',
    async *entries() {},
    getFileHandle: async () => {
      throw new DOMException('missing', 'NotFoundError');
    },
    isSameEntry: async () => false,
    resolve: async () => null,
  };
  let pick = 0;
  dom.window.showDirectoryPicker = async () =>
    pick++ === 0 ? sourceDirectory : output;
  await act(async () =>
    [...document.querySelectorAll('button')]
      .find((button) => button.textContent.startsWith('Wybierz nowe'))
      .click(),
  );
  await act(async () =>
    [...document.querySelectorAll('button')]
      .find((button) => button.textContent.startsWith('Wybierz osobny'))
      .click(),
  );
  const select = document.querySelectorAll('select')[1];
  const save = () =>
    [...document.querySelectorAll('button')].find(
      (button) => button.textContent === 'Przygotuj wybrane zdjęcie',
    );
  await act(async () => {
    select.value = 'seq_1-9.jpg';
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  async function loadVisibleImage() {
    const image = document.querySelector('img');
    assert.ok(image, 'new image URL must be visible before a load event');
    Object.defineProperty(image, 'naturalWidth', {
      configurable: true,
      value: 10,
    });
    Object.defineProperty(image, 'naturalHeight', {
      configurable: true,
      value: 10,
    });
    await act(async () =>
      image.dispatchEvent(new dom.window.Event('load', { bubbles: true })),
    );
    assert.equal(
      save().disabled,
      true,
      'decoded image still requires the 300ms visibility gate',
    );
    await act(async () => new Promise((done) => setTimeout(done, 350)));
  }
  await loadVisibleImage();
  assert.equal(save().disabled, false);
  await act(async () => {
    select.value = 'seq_1-9.jpeg';
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await act(async () => new Promise((done) => setTimeout(done, 400)));
  assert.equal(
    save().disabled,
    true,
    'previous image cannot satisfy the current source gate',
  );
  await act(async () => {
    release(new File(['second'], 'seq_1-9.jpeg'));
  });
  assert.equal(
    save().disabled,
    true,
    'URL availability alone does not prove image decode',
  );
  await loadVisibleImage();
  assert.equal(save().disabled, false);
});
