import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks, createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { readFileSync, existsSync, statSync } from 'node:fs';
import ts from 'typescript';
import React from 'react';

const apiUrl = new URL(
  '../../../packages/vision-lab-api-client/src/index.ts',
  import.meta.url,
).href;
const require = createRequire(import.meta.url);
const reactUrls = Object.fromEntries(
  ['react', 'react/jsx-runtime', 'react/jsx-dev-runtime'].map((specifier) => [
    specifier,
    pathToFileURL(require.resolve(specifier)).href,
  ]),
);
registerHooks({
  resolve(specifier, context, next) {
    if (reactUrls[specifier])
      return { url: reactUrls[specifier], shortCircuit: true };
    if (specifier.startsWith('.')) {
      const url = new URL(specifier, context.parentURL);
      for (const extension of ['', '.ts', '.tsx']) {
        const candidate = new URL(url.href + extension);
        if (existsSync(candidate) && statSync(candidate).isFile())
          return { url: candidate.href, shortCircuit: true };
      }
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === apiUrl)
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export const symbolBatchQueue = () => globalThis.batchApi.read(); export const writeSymbol = (body) => globalThis.batchApi.write(body);',
      };
    if (/\.(tsx|ts)$/.test(url))
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(new URL(url), 'utf8'), {
          compilerOptions: {
            module: ts.ModuleKind.ESNext,
            jsx: ts.JsxEmit.ReactJSX,
            target: ts.ScriptTarget.ES2022,
          },
        }).outputText,
      };
    return next(url, context);
  },
});
const { act, create } = await import('react-test-renderer');
const { SymbolBatchEditor } =
  await import('../src/components/symbol-batch-editor.tsx');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.HTMLElement = class {};
const events = new Map();
globalThis.window = {
  location: { search: '?case=2' },
  addEventListener: (type, handler) => events.set(type, handler),
  removeEventListener: (type) => events.delete(type),
};

function text(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(text).join('');
  return node?.children ? text(node.children) : '';
}
const button = (root, name) =>
  root.root
    .findAllByType('button')
    .find((item) => text(item.toJSON?.() ?? item.props.children) === name);

test('actual editor selects a crop instead of navigating; saves, retries and keeps next choice without reload', async () => {
  let reads = 0,
    rejectFirst;
  const writes = [];
  const page = {
    kind: 'batch_queue',
    reference_id: 'reference',
    revision: 0,
    dictionary: {
      entries: [
        { id: 'a', display_name: 'A' },
        { id: 'b', display_name: 'B' },
      ],
    },
    items: [1, 2].map((id) => ({
      case_id: String(id),
      board: id,
      field: 1,
      filename: 'photo.png',
      category: 'Fixture',
      png_base64: 'exact-PNG-' + id,
      action: null,
      symbol_id: null,
      decision_id: null,
      photo_url: 'http://127.0.0.1:8108/photo',
    })),
  };
  globalThis.batchApi = {
    read: async () => {
      reads++;
      return structuredClone(page);
    },
    write: async (request) => {
      writes.push(request);
      if (writes.length === 1)
        return new Promise((_resolve, reject) => {
          rejectFirst = reject;
        });
      return {
        request_id: request.request_id,
        revision: request.expected_revision + 1,
        result_id: 'decision',
        decision_ids: ['decision'],
        trainable: false,
      };
    },
  };
  let root;
  await act(async () => {
    root = create(React.createElement(SymbolBatchEditor));
  });
  try {
    const crops = () =>
      root.root
        .findAllByType('button')
        .filter((item) => item.props['aria-label']?.startsWith('Wycinek'));
    assert.equal(crops()[1].props['aria-pressed'], true); // deep link
    assert.equal(crops()[1].findAllByType('a').length, 0);
    await act(async () => crops()[0].props.onClick());
    assert.equal(crops()[0].props['aria-pressed'], true);
    assert.equal(writes.length, 0);
    await act(async () =>
      events.get('keydown')({ key: '1', preventDefault() {} }),
    );
    assert.equal(button(root, 'Zapisz symbol').props.disabled, true); // exact PNG not loaded yet
    await act(async () =>
      crops().forEach((crop) => crop.findByType('img').props.onLoad()),
    );
    const pngs = crops().map((crop) => crop.findByType('img').props.src);
    await act(async () => button(root, 'Zapisz symbol').props.onClick());
    assert.equal(writes[0].case_id, '1');
    assert.equal(writes[0].symbol_id, 'a');
    let blocked = false;
    events.get('beforeunload')({
      preventDefault() {
        blocked = true;
      },
    });
    assert.equal(blocked, true);
    await act(async () => {
      crops()[1].props.onClick();
      events.get('keydown')({ key: '2', preventDefault() {} });
    });
    assert.equal(crops()[1].props['aria-pressed'], true);
    await act(async () => rejectFirst(new Error('lost reply')));
    assert.equal(crops()[0].props.disabled, true);
    await act(async () => button(root, 'Ponów ten sam zapis').props.onClick());
    assert.equal(writes[1], writes[0]);
    assert.equal(reads, 1);
    assert.equal(crops()[1].props['aria-pressed'], true);
    assert.deepEqual(
      crops().map((crop) => crop.findByType('img').props.src),
      pngs,
    );
    assert.match(text(root.toJSON()), /Zapisany: A/);
    assert.equal(button(root, 'Zapisz symbol').props.disabled, false);
    await act(async () => button(root, 'Zapisz symbol').props.onClick());
    assert.equal(writes[2].case_id, '2');
    assert.equal(writes[2].symbol_id, 'b');
    assert.equal(writes[2].expected_revision, 1);
    assert.equal(reads, 1);
    await act(async () =>
      button(root, 'Odczytaj zapisane poprawki').props.onClick(),
    );
    await act(async () =>
      events.get('keydown')({ key: '1', preventDefault() {} }),
    );
    assert.equal(button(root, 'Zapisz symbol').props.disabled, true); // refreshed PNGs must load again
    await act(async () =>
      crops().forEach((crop) => crop.findByType('img').props.onLoad()),
    );
    assert.equal(button(root, 'Zapisz symbol').props.disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});
