import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { readFileSync, existsSync, statSync } from 'node:fs';
import ts from 'typescript';
import React from 'react';
import { act, create } from 'react-test-renderer';

// Isolated UI harness: real React components, transport replaced before import.
const apiUrl = new URL(
  '../../../packages/vision-lab-api-client/src/index.ts',
  import.meta.url,
).href;
const nextLinkUrl = new URL('./next-link-harness.mjs', import.meta.url).href;
registerHooks({
  resolve(specifier, context, next) {
    // Next's bundler resolves this extensionless CJS entry and unwraps its
    // default export. Native Node ESM needs both steps explicitly. Keep the
    // real Link implementation: this is resolution, not a replacement anchor.
    if (specifier === 'next/link')
      return { url: nextLinkUrl, shortCircuit: true };
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
    if (url === nextLinkUrl)
      return {
        format: 'module',
        shortCircuit: true,
        source:
          "import entry from 'next/link.js'; export default entry.default ?? entry;",
      };
    if (url === apiUrl)
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export const listRuns = (...args) => globalThis.labApi.runs?.(...args) ?? Promise.resolve({runs: [], total: 0});' +
          'export const assetUrl = (id) => id; export const readAnnotations = (...args) => globalThis.labApi.read(...args); export const writeAnnotation = (...args) => globalThis.labApi.write(...args); export const writePhotoReview = (...args) => globalThis.labApi.review(...args); export const previewGeometry = (...args) => globalThis.labApi.preview(...args); export const listSources = (...args) => globalThis.labApi.list(...args); export const detectGeometry = (...args) => globalThis.labApi.detect?.(...args) ?? Promise.resolve({}); export const writeFamily = async () => ({}); export const backupAnnotations = async () => ({}); export const annotationTimings = async () => []; export const symbolLabels = (...args) => globalThis.labApi.symbolLabels(...args); export const symbolDictionaries = (...args) => globalThis.labApi.symbolDictionaries(...args); export const symbolDictionary = (...args) => globalThis.labApi.symbolDictionary(...args); export const symbolBoard = (...args) => globalThis.labApi.symbolBoard(...args); export const SYMBOL_QUEUE_VIEW_SIZE = 500; export const symbolQueue = (...args) => globalThis.labApi.symbolQueue?.(...args) ?? Promise.resolve({kind: "lab_queue", items: [], total: 0, revision: 0, read_token: "test"}); export const symbolCrop = (...args) => globalThis.labApi.symbolCrop(...args); export const writeSymbol = (...args) => globalThis.labApi.writeSymbol(...args); export const backupSymbols = (...args) => globalThis.labApi.backupSymbols(...args);',
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
const { GeometryEditor } =
  await import('../src/components/geometry-editor.tsx');
const { QuickReview } = await import('../src/components/quick-review.tsx');
const { SymbolLabelEditor } =
  await import('../src/components/symbol-label-editor.tsx');
const { SymbolBoardEditor } =
  await import('../src/components/symbol-board-editor.tsx');
const { SymbolCandidateQueue } =
  await import('../src/components/symbol-candidate-queue.tsx');
const { SymbolAssignedGallery } =
  await import('../src/components/symbol-assigned-gallery.tsx');
const { quickReviewQueue } = await import('../src/lib/quick-review.ts');
const { AnnotationProvider, useAnnotations } =
  await import('../src/components/annotation-context.tsx');
const { default: Page } = await import('../src/app/page.tsx');
const { default: NextLink } = await import('next/link');
const { ToastProvider, useToast } =
  await import('../../../packages/ui/src/toasts.tsx');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test('assigned gallery filters by symbol and refreshes after label writes', async () => {
  const calls = [];
  globalThis.labApi = { symbolQueue: async (...args) => {
    calls.push(args);
    return { kind: 'lab_queue', revision: calls.length, read_token: 'token', total: 1,
      items: [{ binding: { crop_id: 'crop-1', source_id: 's', board_index: 1,
        cell_index: 3 }, png_base64: 'bytes', status: 'assigned' }] };
  } };
  const props = { game: 'g', sources: [{ id: 's', filename: 'photo.jpg' }],
    active: { version: 1, digest: 'dict', entries: [{ id: 'a', display_name: 'Cytryna' }] },
    readVersion: 0, onError: () => {} };
  let root;
  await act(async () => { root = create(React.createElement(SymbolAssignedGallery, props)); });
  try {
    assert.equal(calls.length, 0);
    await act(async () => root.root.findByType('select').props.onChange({ target: { value: 'a' } }));
    assert.deepEqual(calls[0], ['g', 0, undefined, 'a']);
    assert.equal(root.root.findAllByType('img').length, 1);
    assert.match(root.root.findByType('article').findAllByType('span')
      .map((span) => span.children.join(' ')).join(' '), /Plansza\s+2/);
    await act(async () => root.update(React.createElement(SymbolAssignedGallery,
      { ...props, readVersion: 1 })));
    assert.equal(calls.length, 2);
  } finally {
    await act(async () => root.unmount());
  }
});

test('queue component requires loaded pixels and refreshes after image failure', async () => {
  const requests = [], errors = [];
  const page = { kind: 'lab_queue', revision: 2, read_token: 'token', total: 2,
    items: [0, 1].map((cell_index) => ({ binding: { crop_id: `crop${cell_index}`,
      cell_index, source_id: 's', board_index: 0 }, png_base64: 'bytes',
      status: 'unassigned', reason: null })) };
  globalThis.labApi = { symbolQueue: async () => structuredClone(page) };
  const props = { game: 'g', sources: [{ id: 's', filename: 'photo.jpg' }],
    active: { version: 1, digest: 'dict', entries: [{ id: 'a', display_name: 'Cytryna' }] },
    readVersion: 0, enabled: true, disabled: false, onBusy: () => {},
    onError: (error) => errors.push(error), onSubmit: async (request) => requests.push(request) };
  let root;
  await act(async () => { root = create(React.createElement(SymbolCandidateQueue, props)); });
  try {
    const images = root.root.findAllByType('img');
    assert.equal(images.length, 2);
    assert.equal(root.root.findAllByType('input')[0].props.disabled, true);
    await act(async () => images[0].props.onLoad());
    const checkbox = root.root.findAllByType('input')[0];
    assert.equal(checkbox.props.disabled, false);
    await act(async () => checkbox.props.onChange({ target: { checked: true } }));
    await act(async () => root.root.findByType('select').props.onChange({ target: { value: 'a' } }));
    await act(async () => button(root, 'Przypisz zaznaczone (1)').props.onClick());
    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0].bindings, [page.items[0].binding]);
    await act(async () => root.update(React.createElement(SymbolCandidateQueue, {
      ...props, active: { version: 2, digest: 'new-dict',
        entries: [{ id: 'b', display_name: 'Jabłko' }] },
    })));
    assert.equal(root.root.findByType('select').props.value, '');
    assert.equal(button(root, 'Przypisz zaznaczone (1)').props.disabled, true);
    await act(async () => images[1].props.onError());
    assert.equal(root.root.findAllByType('input')[1].props.disabled, true);
    const oldImageOnLoad = images[0].props.onLoad;
    await act(async () => button(root, 'Odśwież poczekalnię').props.onClick());
    assert.equal(errors.length, 1);
    assert.equal(root.root.findAllByType('input')[0].props.disabled, true);
    await act(async () => oldImageOnLoad());
    assert.equal(root.root.findAllByType('input')[0].props.disabled, true);
    await act(async () => root.root.findAllByType('img')[0].props.onLoad());
    assert.equal(root.root.findAllByType('input')[0].props.disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});

test('queue waits for parent read and reports a real API error code', async () => {
  let calls = 0;
  const errors = [];
  globalThis.labApi = { symbolQueue: async () => {
    calls++;
    throw { detail: 'HOLDOUT_POLICY_UNRESOLVED' };
  } };
  const props = { game: 'g', sources: [], active: null, readVersion: 0,
    enabled: false, disabled: true, onBusy: () => {},
    onError: (message) => errors.push(message), onSubmit: async () => {} };
  let root;
  await act(async () => { root = create(React.createElement(SymbolCandidateQueue, props)); });
  try {
    assert.equal(calls, 0);
    assert.deepEqual(errors, []);
    await act(async () => root.update(React.createElement(SymbolCandidateQueue,
      { ...props, enabled: true, disabled: false })));
    assert.equal(calls, 1);
    assert.deepEqual(errors, ['Nie można odczytać poczekalni: HOLDOUT_POLICY_UNRESOLVED']);
  } finally {
    await act(async () => root.unmount());
  }
});

test('whole-board component requires all images, preserves selection after reload and rejects late image events', async () => {
  const requests = [],
    errors = [];
  const board = {
    kind: 'lab_board',
    revision: 2,
    topology: { columns: 5, rows: 3 },
    dictionary: {
      version: 1,
      digest: 'dict',
      entries: [{ id: 'a', display_name: 'Wiśnia' }],
    },
    width: 500,
    height: 300,
    board_png_base64: 'board',
    nodes: Array.from({ length: 24 }, (_, i) => ({
      x: (i % 6) * 100,
      y: Math.floor(i / 6) * 100,
    })),
    cells: Array.from({ length: 15 }, (_, i) => ({
      binding: { cell_index: i, crop_id: `crop${i}` },
      png_base64: `cell${i}`,
      current: null,
    })),
  };
  globalThis.labApi = { symbolBoard: async () => structuredClone(board) };
  const props = {
    game: 'g',
    sources: [{ id: 's', game_id: 'g', filename: 'source' }],
    annotations: {
      revision: 1,
      annotations: {
        's:0': {
          source_id: 's',
          board_index: 0,
          revision: 1,
          full_approved: true,
          presence: 'present',
        },
      },
    },
    revision: 2,
    readVersion: 0,
    disabled: false,
    onBusy: () => {},
    onError: (e) => errors.push(e),
    onSubmit: async (body) => requests.push(body),
  };
  let root;
  await act(async () => {
    root = create(React.createElement(SymbolBoardEditor, props));
  });
  try {
    await act(async () => {
      root.root
        .findAllByType('select')[0]
        .props.onChange({ target: { value: 's' } });
    });
    const selects = () =>
      root.root
        .findAllByType('select')
        .filter((s) => s.props['aria-label']?.startsWith('Symbol pola'));
    assert.equal(selects().length, 15);
    assert.equal(root.root.findAllByType('img').length, 16);
    const numbers = root.root.findAllByType('text');
    assert.equal(numbers.length, 15);
    for (const number of numbers) {
      assert.equal((number.props.style.fontSize * 640) / board.width, 14);
      assert.equal((number.props.style.strokeWidth * 640) / board.width, 3);
    }
    assert.equal(numbers[0].props.x, 50);
    assert.equal(numbers[0].props.y, 50);
    assert.equal(requests.length, 0);
    for (let i = 0; i < 15; i++)
      await act(async () =>
        selects()[i].props.onChange({ target: { value: 'class:a' } }),
      );
    assert.equal(button(root, 'Zapisz wszystkie 15 pól').props.disabled, true);
    const oldImages = root.root.findAllByType('img').map((img) => img.props);
    await act(async () => {
      for (const img of oldImages) img.onLoad();
    });
    assert.equal(button(root, 'Zapisz wszystkie 15 pól').props.disabled, false);
    await act(async () =>
      button(root, 'Zapisz wszystkie 15 pól').props.onClick(),
    );
    assert.equal(requests.length, 1);
    assert.equal(requests[0].cells.length, 15);
    await act(async () =>
      button(root, 'Odczytaj planszę ponownie').props.onClick(),
    );
    assert.equal(root.root.findAllByType('select')[0].props.value, 's');
    await act(async () => {
      for (const img of oldImages) img.onLoad();
      oldImages[0].onError();
    });
    assert.equal(errors.length, 0);
    for (let i = 0; i < 15; i++)
      await act(async () =>
        selects()[i].props.onChange({ target: { value: 'state:unknown' } }),
      );
    assert.equal(button(root, 'Zapisz wszystkie 15 pól').props.disabled, true);
    await act(async () => {
      for (const img of root.root.findAllByType('img')) img.props.onLoad();
    });
    assert.equal(button(root, 'Zapisz wszystkie 15 pól').props.disabled, false);
    await act(async () => root.root.findAllByType('img')[0].props.onError());
    assert.equal(errors.length, 1);
    assert.equal(button(root, 'Zapisz wszystkie 15 pól').props.disabled, true);
    assert.doesNotMatch(text(root.toJSON()), /Nie udało się wczytać obrazu/);
    let guardedReads = 0;
    globalThis.labApi.symbolBoard = async () => {
      guardedReads++;
      throw Error('HOLDOUT_NOT_RELEASED');
    };
    await act(async () =>
      root.update(
        React.createElement(SymbolBoardEditor, {
          ...props,
          annotations: { ...props.annotations, revision: 2 },
        }),
      ),
    );
    assert.equal(guardedReads, 1);
    assert.equal(root.root.findAllByType('img').length, 0);
    assert.match(errors.at(-1), /HOLDOUT_NOT_RELEASED/);
    globalThis.labApi.symbolBoard = async () => structuredClone(board);
    await act(async () =>
      root.update(
        React.createElement(SymbolBoardEditor, { ...props, readVersion: 1 }),
      ),
    );
    assert.equal(root.root.findAllByType('img').length, 16);
    await act(async () =>
      root.update(
        React.createElement(SymbolBoardEditor, {
          ...props,
          readVersion: 1,
          annotations: { revision: 3, annotations: {} },
        }),
      ),
    );
    assert.equal(root.root.findAllByType('img').length, 0);
    assert.match(text(root.toJSON()), /Brak zapisanej pełnej geometrii/);
    await act(async () =>
      root.update(
        React.createElement(SymbolBoardEditor, { ...props, disabled: true }),
      ),
    );
    assert.equal(root.root.findByType('fieldset').props.disabled, true);
  } finally {
    await act(async () => root.unmount());
  }
});
globalThis.window = {
  setTimeout,
  clearTimeout,
  addEventListener(type) {
    assert.notEqual(type, 'beforeunload');
  },
  removeEventListener() {},
  confirm() {
    throw new Error('Browser confirmation is forbidden in lab workflow');
  },
};
// Real NextLink uses the browser's self timer fallback for intersection work.
globalThis.self = globalThis.window;
globalThis.document = {
  addEventListener() {},
  removeEventListener() {},
  hidden: false,
  getElementById() {
    return null;
  },
};
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
const source = { id: 'source', asset_id: 'photo', sha256: 'a'.repeat(64) };
test('real NextLink resolves and renders its navigation anchor in the Node harness', async () => {
  let root;
  await act(async () => {
    root = create(
      React.createElement(NextLink, { href: '/symbols' }, 'Etykiety symboli'),
    );
  });
  try {
    const anchor = root.root.findByType('a');
    assert.equal(anchor.props.href, '/symbols');
    assert.equal(anchor.props.children, 'Etykiety symboli');
    assert.equal(typeof anchor.props.onClick, 'function');
  } finally {
    await act(async () => root.unmount());
  }
});
test('parent reload stays disabled while queue reads a selected game', async () => {
  let finishQueue;
  const source = { id: 's', game_id: 'g', game_name: 'Gra', filename: 'photo.jpg' };
  globalThis.labApi = {
    read: async () => ({ revision: 1, annotations: {} }),
    list: async () => ({ sources: [source], total: 1 }),
    symbolLabels: async () => ({ items: [], revision: 0, total: 0, read_token: 'labels' }),
    symbolDictionaries: async () => ({ items: [], total: 0, read_token: 'dict' }),
    symbolQueue: () => new Promise((resolve) => { finishQueue = resolve; }),
  };
  let root;
  await act(async () => {
    root = create(React.createElement(ToastProvider, null,
      React.createElement(AnnotationProvider, null,
        React.createElement(SymbolLabelEditor))));
  });
  try {
    await act(async () => root.root.findAllByType('select')[0].props.onChange(
      { target: { value: 'g' } }));
    assert.equal(typeof finishQueue, 'function');
    assert.equal(button(root, 'Odczytaj stan').props.disabled, true);
    await act(async () => finishQueue({ kind: 'lab_queue', items: [], total: 0,
      revision: 0, read_token: 'queue' }));
    assert.equal(button(root, 'Odczytaj stan').props.disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});
test('symbol dictionary exposes only a name, validates it and preserves generated identity in the save payload', async () => {
  const requests = [];
  const symbolSource = {
    ...source,
    game_id: 'game',
    game_name: 'Gra',
    filename: 'source.png',
    role: 'development',
  };
  globalThis.labApi = {
    read: async () => ({ revision: 1, annotations: {} }),
    list: async () => ({ sources: [symbolSource], total: 1 }),
    symbolLabels: async () => ({
      items: [],
      revision: 0,
      total: 0,
      read_token: undefined,
    }),
    symbolDictionaries: async () => ({
      items: [
        {
          origin: 'lab',
          version: 2,
          digest: 'draft-digest',
          status: 'draft',
          active: false,
        },
      ],
      total: 1,
      read_token: undefined,
    }),
    symbolDictionary: async () => ({
      entries: [
        {
          id: 'legacy-id',
          code: 'legacy-code',
          display_name: 'Dzwonek',
        },
      ],
    }),
    symbolCrop: async () => ({}),
    writeSymbol: async (request) => requests.push(request),
    backupSymbols: async () => ({}),
  };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(SymbolLabelEditor),
        ),
      ),
    );
  });
  try {
    await act(async () => {
      root.root
        .findAllByType('select')
        .at(0)
        .props.onChange({ target: { value: 'game' } });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await act(async () => button(root, 'Dodaj klasę').props.onClick());
    const dictionary = root.root
      .findAllByType('fieldset')
      .find((node) => text(node).includes('Słownik gry'));
    assert.equal(dictionary.findAllByType('input').length, 2);
    assert.doesNotMatch(text(dictionary), /\bID\b|\bKod\b/);
    await act(async () => button(root, 'Zapisz nową wersję').props.onClick());
    assert.equal(requests.length, 0);
    assert.match(text(root.toJSON()), /Nazwa symbolu nie może być pusta/);
    const [legacyName, newName] = dictionary.findAllByType('input');
    await act(async () =>
      legacyName.props.onChange({ target: { value: '  Wiśnia  ' } }),
    );
    await act(async () =>
      newName.props.onChange({ target: { value: '  Winogrono  ' } }),
    );
    await act(async () => {
      button(root, 'Zapisz nową wersję').props.onClick();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    assert.equal(requests.length, 1);
    const [legacy, entry] = requests[0].entries;
    assert.deepEqual(legacy, {
      id: 'legacy-id',
      code: 'legacy-code',
      display_name: 'Wiśnia',
    });
    assert.match(
      entry.id,
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
    assert.equal(entry.code, `symbol_${entry.id}`);
    assert.equal(entry.display_name, 'Winogrono');
  } finally {
    await act(async () => root.unmount());
  }
});
const points = (columns, offset = 0) =>
  Array.from({ length: 4 * (columns + 1) }, (_, i) => ({
    x: offset + 10 + (i % (columns + 1)) * 20,
    y: 10 + Math.floor(i / (columns + 1)) * 20,
    provenance: 'human',
  }));
const annotation = (index, columns = 5) => {
  const nodes = points(columns, index * 3);
  return {
    source_id: 'source',
    board_index: index,
    topology: { columns, rows: 3 },
    presence: 'present',
    nodes,
    corners: [
      nodes[0],
      nodes[columns],
      nodes.at(-1),
      nodes[nodes.length - columns - 1],
    ],
    full_approved: true,
    location_approved: true,
    revision: 1,
    actor: 'original',
  };
};
const text = (node) =>
  typeof node === 'string'
    ? node
    : (Array.isArray(node) ? node : (node.children ?? [])).map(text).join('');
function button(root, label) {
  return root.root.findAllByType('button').find((node) => text(node) === label);
}
async function mountQuick(
  initial,
  sources = [source, { ...source, id: 'other', asset_id: 'other' }],
) {
  let stored = initial,
    shared,
    fail = false,
    returned = 0;
  const requests = [],
    receipts = new Map();
  function Observer() {
    shared = useAnnotations();
    return null;
  }
  globalThis.labApi = {
    read: async () => stored,
    review: async (body) => {
      requests.push(body);
      if (receipts.has(body.request_id)) return receipts.get(body.request_id);
      stored = {
        ...stored,
        revision: stored.revision + 1,
        photo_reviews: {
          ...stored.photo_reviews,
          [body.source_id]: {
            source_id: body.source_id,
            source_sha256: body.source_sha256,
            accepted_board_revisions:
              body.action === 'accept' ? body.expected_board_revisions : {},
            rejected: body.action === 'reject',
            issues: {},
          },
        },
      };
      receipts.set(body.request_id, stored);
      if (fail) {
        fail = false;
        throw new Error('response lost');
      }
      return stored;
    },
  };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(Observer),
          React.createElement(QuickReview, {
            sources,
            initialState: initial,
            game: '',
            onReturn: () => returned++,
          }),
        ),
      ),
    );
  });
  return {
    root,
    requests,
    get stored() {
      return stored;
    },
    get returned() {
      return returned;
    },
    failOnce() {
      fail = true;
    },
    accept: async (value) => act(async () => shared.accept(value)),
    setRead: (read) => {
      globalThis.labApi.read = read;
    },
    setWrite: (write) => {
      globalThis.labApi.review = write;
    },
    async loadImage() {
      await act(async () =>
        root.root
          .findByProps({ className: 'quick-source-loader' })
          .props.onLoad({
            currentTarget: { naturalWidth: 1000, naturalHeight: 700 },
          }),
      );
      await act(async () => root.root.findByType('image').props.onLoad());
    },
  };
}
const quickInitial = () => ({
  revision: 1,
  annotations: {
    'source:0': annotation(0),
    'source:12': annotation(12, 3),
    'other:0': { ...annotation(0), source_id: 'other' },
  },
});

test('quick queue preserves catalog order/game and excludes rejected, accepted, corrections and nonfull photos', () => {
  const ids = [
    'review',
    'rejected',
    'accepted',
    'fix',
    'draft',
    'recheck',
    'othergame',
  ];
  const sources = ids.map((id) => ({
    ...source,
    id,
    game_id: id === 'othergame' ? 'b' : 'a',
  }));
  const state = {
    revision: 1,
    annotations: Object.fromEntries(
      ids.map((id) => [
        `${id}:0`,
        { ...annotation(0), source_id: id, full_approved: id !== 'draft' },
      ]),
    ),
    photo_reviews: {
      rejected: { rejected: true },
      accepted: {
        source_sha256: source.sha256,
        accepted_board_revisions: { 0: 1 },
      },
      fix: { issues: { 0: { status: 'needs_correction' } } },
      recheck: { issues: { 0: { status: 'needs_review' } } },
    },
  };
  assert.deepEqual(
    quickReviewQueue(sources, state, 'a').map((s) => s.id),
    ['review', 'recheck'],
  );
  assert.deepEqual(
    quickReviewQueue(sources, state).map((s) => s.id),
    ['review', 'recheck', 'othergame'],
  );
});

test('quick review gates visible image, shows every saved grid and advances exactly once per explicit decision', async () => {
  const h = await mountQuick(quickInitial());
  let persisted;
  try {
    assert.equal(button(h.root, 'Zatwierdź').props.disabled, true);
    await act(async () =>
      button(h.root, 'Zatwierdź').props.onClick({ detail: 1 }),
    );
    assert.equal(h.requests.length, 0);
    await act(async () =>
      h.root.root
        .findByProps({ className: 'quick-source-loader' })
        .props.onLoad({
          currentTarget: { naturalWidth: 1000, naturalHeight: 700 },
        }),
    );
    assert.equal(button(h.root, 'Zatwierdź').props.disabled, true);
    await act(async () => h.root.root.findByType('image').props.onLoad());
    assert.equal(h.root.root.findAllByType('polygon').length, 2);
    assert.equal(h.root.root.findAllByType('polyline').length, 18);
    assert.match(text(h.root.toJSON()), /13/);
    await act(async () =>
      button(h.root, 'Zatwierdź').props.onClick({ detail: 1 }),
    );
    assert.deepEqual(h.requests[0].expected_board_revisions, { 0: 1, 12: 1 });
    assert.match(text(h.root.toJSON()), /Zdjęcie 2 z 2/);
    assert.equal(button(h.root, 'Odrzuć').props.disabled, true);
    await h.loadImage();
    await act(async () =>
      button(h.root, 'Odrzuć').props.onClick({ detail: 2 }),
    );
    assert.equal(h.requests.length, 1);
    await act(async () => h.root.root.findByType('image').props.onError());
    await act(async () =>
      button(h.root, 'Odrzuć').props.onClick({ detail: 1 }),
    );
    assert.equal(h.requests.length, 1);
    await act(async () =>
      button(h.root, 'Odśwież zdjęcie i stan').props.onClick(),
    );
    await h.loadImage();
    await act(async () =>
      button(h.root, 'Odrzuć').props.onClick({ detail: 1 }),
    );
    assert.match(text(h.root.toJSON()), /Koniec kolejki/);
    assert.equal(h.requests.length, 2);
    persisted = h.stored;
  } finally {
    await act(async () => h.root.unmount());
  }
  const restarted = await mountQuick(persisted);
  try {
    assert.match(text(restarted.root.toJSON()), /Koniec kolejki/);
    assert.equal(restarted.requests.length, 0);
  } finally {
    await act(async () => restarted.root.unmount());
  }
});

test('quick review lost response keeps exact retry and exit lock after toast expires', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  let clock = 0;
  t.mock.method(performance, 'now', () => clock);
  const h = await mountQuick(quickInitial());
  try {
    await h.loadImage();
    h.failOnce();
    const approve = button(h.root, 'Zatwierdź');
    await act(async () => {
      approve.props.onClick({ detail: 1 });
      approve.props.onClick({ detail: 1 });
    });
    assert.equal(h.requests.length, 1);
    assert.match(text(h.root.toJSON()), /Zdjęcie 1 z 2/);
    await act(async () => {
      clock += 4000;
      t.mock.timers.tick(250);
    });
    assert.equal(
      h.root.root.findAllByProps({
        className: 'shared-toast shared-toast-error',
      }).length,
      0,
    );
    assert.equal(button(h.root, 'Powrót do edycji').props.disabled, true);
    await act(async () => button(h.root, 'Powrót do edycji').props.onClick());
    assert.equal(h.returned, 0);
    await act(async () =>
      button(h.root, 'Ponów identyczną decyzję').props.onClick(),
    );
    assert.equal(h.requests[0], h.requests[1]);
    assert.match(text(h.root.toJSON()), /Zdjęcie 2 z 2/);
  } finally {
    await act(async () => h.root.unmount());
  }
});

test('quick review stale response/read or changed receipt geometry never advances', async () => {
  const h = await mountQuick(quickInitial());
  try {
    await h.loadImage();
    let resolve;
    h.setWrite(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await act(async () =>
      button(h.root, 'Zatwierdź').props.onClick({ detail: 1 }),
    );
    await h.accept({ ...quickInitial(), revision: 10 });
    await act(async () => resolve({ ...quickInitial(), revision: 2 }));
    assert.match(text(h.root.toJSON()), /Zdjęcie 1 z 2/);
    h.setRead(async () => ({ ...quickInitial(), revision: 3 }));
    await act(async () =>
      button(h.root, 'Odśwież zdjęcie i stan').props.onClick(),
    );
    assert.equal(button(h.root, 'Powrót do edycji').props.disabled, true);
    const changed = quickInitial();
    changed.revision = 11;
    changed.annotations['source:0'].revision = 11;
    h.setWrite(async () => changed);
    await act(async () =>
      button(h.root, 'Ponów identyczną decyzję').props.onClick(),
    );
    assert.match(text(h.root.toJSON()), /Zdjęcie 1 z 2/);
    assert.equal(button(h.root, 'Powrót do edycji').props.disabled, true);
    h.setRead(async () => changed);
    await act(async () =>
      button(h.root, 'Odśwież zdjęcie i stan').props.onClick(),
    );
    assert.equal(button(h.root, 'Powrót do edycji').props.disabled, false);
    assert.equal(button(h.root, 'Zatwierdź').props.disabled, true);
  } finally {
    await act(async () => h.root.unmount());
  }
});
async function mount(initial) {
  const requests = [],
    previews = [];
  const replies = new Map();
  const reviewRequests = [];
  let stored = initial;
  let fail = false;
  let shared;
  function Observer() {
    shared = useAnnotations();
    return null;
  }
  globalThis.labApi = {
    read: async () => stored,
    preview: async (...args) => {
      previews.push(args);
      return { status: 'detected', boards: [] };
    },
    write: async (body) => {
      requests.push(body);
      if (replies.has(body.request_id)) return replies.get(body.request_id);
      stored = {
        ...stored,
        revision: stored.revision + 1,
        annotations: {
          ...stored.annotations,
          [`source:${body.annotation.board_index}`]: {
            ...body.annotation,
            revision: stored.revision + 1,
            full_approved: body.action === 'approve_full',
            location_approved: body.action !== 'draft',
          },
        },
      };
      if (stored.photo_reviews?.source) {
        const review = structuredClone(stored.photo_reviews.source);
        review.accepted_board_revisions = {};
        const issue = review.issues?.[String(body.annotation.board_index)];
        if (issue) {
          issue.status = 'needs_review';
          issue.board_revision =
            stored.annotations[
              `source:${body.annotation.board_index}`
            ].revision;
        }
        stored = {
          ...stored,
          photo_reviews: { ...stored.photo_reviews, source: review },
        };
      }
      replies.set(body.request_id, stored);
      if (fail) {
        fail = false;
        throw new Error('lost response after commit');
      }
      return stored;
    },
    review: async (body) => {
      reviewRequests.push(body);
      if (replies.has(body.request_id)) return replies.get(body.request_id);
      const review = structuredClone(
        stored.photo_reviews?.source ?? {
          source_id: 'source',
          source_sha256: source.sha256,
          accepted_board_revisions: {},
          issues: {},
        },
      );
      if (body.action === 'mark') {
        review.accepted_board_revisions = {};
        for (const index of body.board_indices)
          review.issues[String(index)] = {
            status: 'needs_correction',
            board_revision: stored.annotations[`source:${index}`].revision,
            note: body.note,
            actor: 'operator',
            decided_at: 'test',
          };
      } else if (body.action === 'withdraw') {
        for (const index of body.board_indices)
          delete review.issues[String(index)];
        review.accepted_board_revisions = {};
      } else {
        review.accepted_board_revisions = body.expected_board_revisions;
        review.issues = {};
        review.rejected = false;
      }
      stored = {
        ...stored,
        revision: stored.revision + 1,
        photo_reviews: { ...stored.photo_reviews, source: review },
      };
      replies.set(body.request_id, stored);
      if (fail) {
        fail = false;
        throw new Error('review response lost after commit');
      }
      return stored;
    },
  };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(Observer),
          React.createElement(GeometryEditor, {
            source,
            columns: 5,
            proposal: null,
            onProtectionChange() {},
            onColumnsChange() {},
          }),
        ),
      ),
    );
  });
  await act(async () =>
    root.root.findByProps({ className: 'editor-source-loader' }).props.onLoad({
      currentTarget: { naturalWidth: 500, naturalHeight: 400 },
    }),
  );
  return {
    root,
    requests,
    reviewRequests,
    previews,
    failOnce: () => {
      fail = true;
    },
    setRead: (fn) => {
      globalThis.labApi.read = fn;
    },
    accept: (value) => shared.accept(value),
  };
}
test('explicit full approval uses operator, advances once and loads exact existing topology/crops', async () => {
  const saved = annotation(1, 3);
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0), 'source:1': saved },
  });
  try {
    const approve = button(harness.root, 'Zatwierdź pełną siatkę');
    await act(async () => {
      const first = approve.props.onClick();
      approve.props.onClick();
      await first;
    });
    assert.equal(harness.requests.length, 1);
    assert.equal(harness.requests[0].actor, 'operator');
    assert.equal(harness.requests[0].reviewed_all_nodes, true);
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    assert.deepEqual(harness.previews.at(-1), [
      'source',
      3,
      { position_index: 1, status: 'complete', nodes: saved.nodes },
    ]);
    assert.doesNotMatch(text(harness.root.toJSON()), /Sprawdziłem każdy węzeł/);
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('unflagged geometry keeps auto-next even after a previous photo review', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0), 'source:1': annotation(1) },
    photo_reviews: {
      source: {
        source_id: 'source',
        source_sha256: source.sha256,
        accepted_board_revisions: { 0: 1, 1: 1 },
        issues: {},
      },
    },
  });
  try {
    harness.failOnce();
    await act(async () =>
      button(harness.root, 'Zatwierdź pełną siatkę').props.onClick(),
    );
    await act(async () =>
      button(
        harness.root,
        'Ponów identyczne żądanie: approve_full',
      ).props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    assert.equal(
      harness.requests[0].request_id,
      harness.requests[1].request_id,
    );
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('photo review mark and full repair stay on the corrected board until explicit whole-photo acceptance', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0), 'source:4': annotation(4) },
  });
  try {
    const panel = () =>
      harness.root.root.findByProps({
        'aria-label': 'Przegląd całego zdjęcia',
      });
    assert.equal(harness.root.root.findByType('details').props.open, undefined);
    await act(async () =>
      panel()
        .findAllByProps({ type: 'checkbox' })[0]
        .props.onChange({ target: { checked: true } }),
    );
    await act(async () =>
      panel()
        .findByType('textarea')
        .props.onChange({ target: { value: 'Róg do poprawy' } }),
    );
    await act(async () =>
      button(harness.root, 'Oznacz wybrane: Do poprawy').props.onClick(),
    );
    assert.deepEqual(harness.reviewRequests[0].board_indices, [0]);
    assert.equal(harness.reviewRequests[0].note, 'Róg do poprawy');
    assert.deepEqual(harness.reviewRequests[0].expected_board_revisions, {
      0: 1,
      4: 1,
    });
    assert.match(text(panel()), /Do poprawy: 1/);
    assert.equal(
      button(harness.root, 'Akceptuj całe zdjęcie').props.disabled,
      true,
    );
    await act(async () =>
      button(harness.root, 'Zatwierdź pełną siatkę').props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      1,
    );
    assert.match(text(panel()), /Do ponownego sprawdzenia: 1/);
    assert.equal(
      button(harness.root, 'Akceptuj całe zdjęcie').props.disabled,
      false,
    );
    await act(async () =>
      button(harness.root, 'Akceptuj całe zdjęcie').props.onClick(),
    );
    assert.equal(harness.reviewRequests.length, 2);
    assert.equal(harness.reviewRequests[1].action, 'accept');
    assert.match(text(panel()), /Zaakceptowane/);
    assert.equal(harness.requests.length, 1);
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('explicit review reconciliation needs no dialog and keeps navigation locked until read completes', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0) },
  });
  try {
    harness.failOnce();
    await act(async () =>
      button(harness.root, 'Akceptuj całe zdjęcie').props.onClick(),
    );
    let resolve;
    harness.setRead(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await act(async () => {
      void button(
        harness.root,
        'Odśwież przegląd po konflikcie',
      ).props.onClick();
    });
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      true,
    );
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '2' } }),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      1,
    );
    await act(async () =>
      resolve({ revision: 2, annotations: { 'source:0': annotation(0) } }),
    );
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      false,
    );
    assert.equal(harness.reviewRequests.length, 1);
    assert.equal(harness.requests.length, 0);
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('review response loss retains exact request, blocks geometry, and retry never repeats a new decision', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0) },
  });
  try {
    harness.failOnce();
    const accept = button(harness.root, 'Akceptuj całe zdjęcie');
    await act(async () => {
      const first = accept.props.onClick();
      accept.props.onClick();
      await first;
    });
    assert.equal(harness.reviewRequests.length, 1);
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      true,
    );
    assert.equal(
      button(harness.root, 'Odśwież po konflikcie').props.disabled,
      true,
    );
    await act(async () =>
      harness.root.root
        .findByProps({ className: 'shared-toast shared-toast-error' })
        .props.onClick(),
    );
    await act(async () =>
      button(
        harness.root,
        'Ponów identyczną decyzję przeglądu',
      ).props.onClick(),
    );
    assert.equal(harness.reviewRequests[0], harness.reviewRequests[1]);
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      false,
    );
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('ordinary review can explicitly accept globally rejected photo without fixing every board', async () => {
  const h = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0) },
    photo_reviews: {
      source: {
        source_id: 'source',
        source_sha256: source.sha256,
        rejected: true,
        issues: {},
        accepted_board_revisions: {},
      },
    },
  });
  try {
    assert.equal(button(h.root, 'Akceptuj całe zdjęcie').props.disabled, false);
    await act(async () =>
      button(h.root, 'Akceptuj całe zdjęcie').props.onClick(),
    );
    assert.match(text(h.root.toJSON()), /Zaakceptowane/);
    assert.equal(h.requests.length, 0);
  } finally {
    await act(async () => h.root.unmount());
  }
});

test('dirty geometry prevents acceptance and a draft correction cannot be accepted as repaired', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0), 'source:4': annotation(4) },
    photo_reviews: {
      source: {
        source_id: 'source',
        source_sha256: source.sha256,
        accepted_board_revisions: {},
        issues: {
          0: { status: 'needs_correction', note: '', board_revision: 1 },
        },
      },
    },
  });
  try {
    await act(async () =>
      button(harness.root, 'Nowa propozycja z narożników').props.onClick(),
    );
    assert.equal(
      button(harness.root, 'Akceptuj całe zdjęcie').props.disabled,
      true,
    );
    await act(async () => button(harness.root, 'Zapisz szkic').props.onClick());
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      1,
    );
    assert.equal(
      button(harness.root, 'Akceptuj całe zdjęcie').props.disabled,
      true,
    );
    assert.match(
      text(
        harness.root.root.findByProps({
          'aria-label': 'Przegląd całego zdjęcia',
        }),
      ),
      /Do ponownego sprawdzenia: 1/,
    );
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('changing topology on a missing position preserves that position and creates the requested grid', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0, 5) },
  });
  try {
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '2' } }),
    );
    const topology = harness.root.root
      .findAllByType('select')
      .find((node) => node.props.value === 5);
    await act(async () => topology.props.onChange({ target: { value: '3' } }));
    await act(async () =>
      button(harness.root, 'Nowa propozycja z narożników').props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    assert.equal(harness.previews.at(-1)[1], 3);
    assert.equal(harness.previews.at(-1)[2].nodes.length, 16);
    await act(async () => button(harness.root, 'Zapisz szkic').props.onClick());
    assert.equal(harness.requests[0].annotation.topology.columns, 3);
    assert.equal(harness.requests[0].annotation.board_index, 1);
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '1' } }),
    );
    assert.equal(
      harness.root.root
        .findAllByType('select')
        .find((node) => node.props.value === 5)?.props.value,
      5,
    );
    assert.equal(harness.previews.at(-1)[2].nodes.length, 24);
  } finally {
    await act(async () => harness.root.unmount());
  }
});
test('shared family revision is used on save, but a changed board revision cannot silently overwrite another editor', async () => {
  const first = annotation(0);
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': first },
  });
  try {
    await act(async () =>
      harness.accept({ revision: 7, annotations: { 'source:0': first } }),
    );
    await act(async () => button(harness.root, 'Zapisz szkic').props.onClick());
    assert.equal(harness.requests[0].expected_revision, 7);
    await act(async () =>
      harness.accept({
        revision: 8,
        annotations: { 'source:0': { ...first, revision: 8 } },
      }),
    );
    await act(async () => button(harness.root, 'Zapisz szkic').props.onClick());
    assert.equal(harness.requests.length, 1);
  } finally {
    await act(async () => harness.root.unmount());
  }
});
test('gallery filter finds approvals beyond first source page and restores persisted counts on mount', async () => {
  const sources = Array.from({ length: 30 }, (_, i) => ({
    id: `s${i}`,
    game_id: 'game',
    game_name: 'Gra',
    asset_id: `p${i}`,
    filename: `photo${i}`,
    duplicate_count: 1,
  }));
  const saved = { ...annotation(0), source_id: 's29' };
  const offsets = [];
  globalThis.labApi = {
    read: async () => ({ revision: 9, annotations: { 's29:0': saved } }),
    preview: async () => ({ status: 'detected', boards: [] }),
    list: async (offset = 0) => {
      offsets.push(offset);
      return {
        sources: sources.slice(offset, offset + 24),
        total: 30,
        games: { game: 'Gra' },
      };
    },
  };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(Page),
        ),
      ),
    );
  });
  try {
    assert.deepEqual(offsets, [0, 24]);
    const filter = root.root
      .findAllByType('select')
      .find((node) => node.props.value === 'all');
    await act(async () => filter.props.onChange({ target: { value: 'full' } }));
    const gallery = root.root.findByProps({ 'aria-label': 'Zdjęcia źródłowe' });
    assert.equal(gallery.findAllByType('button').length, 1);
    assert.match(text(gallery), /photo29/);
    assert.match(text(gallery), /Pełne: 1/);
    await act(async () => gallery.findByType('button').props.onClick());
    await act(async () =>
      root.root
        .findByProps({ className: 'editor-source-loader' })
        .props.onLoad({
          currentTarget: { naturalWidth: 500, naturalHeight: 400 },
        }),
    );
    await act(async () =>
      button(root, 'Nowa propozycja z narożników').props.onClick(),
    );
    const topology = root.root
      .findAllByType('select')
      .find((node) => node.props.value === 5);
    await act(async () => topology.props.onChange({ target: { value: '3' } }));
    assert.equal(
      root.root.findAllByType('select').some((node) => node.props.value === 3),
      true,
    );
    await act(async () => filter.props.onChange({ target: { value: 'all' } }));
    assert.equal(
      root.root
        .findAllByType('select')
        .find((node) => node.props.value === 'all')?.props.value,
      'all',
    );
    const game = root.root
      .findAllByType('select')
      .find((node) => node.props.value === '');
    await act(async () => game.props.onChange({ target: { value: 'game' } }));
    assert.equal(
      root.root
        .findAllByType('select')
        .some((node) => node.props.value === 'game'),
      true,
    );
  } finally {
    await act(async () => root.unmount());
  }
});
test('hybrid model selection stays opt-in and shows best epoch without writing annotations', async () => {
  const calls = [];
  const run = {
    id: 'a'.repeat(32),
    status: 'succeeded',
    best_epoch: 3,
    request: { model_version: 'hybrid-mobilenet-v1' },
  };
  globalThis.labApi = {
    read: async () => ({ revision: 1, annotations: {} }),
    list: async () => ({
      sources: [
        {
          ...source,
          game_id: 'game',
          game_name: 'Gra',
          filename: 'fixture',
          duplicate_count: 1,
        },
      ],
      total: 1,
      games: { game: 'Gra' },
    }),
    runs: async () => ({
      runs: [run, { ...run, id: 'b'.repeat(32), status: 'failed' }],
      total: 2,
    }),
    detect: async (...args) => {
      calls.push(args);
      return {
        source_id: 'source',
        status: 'detected',
        boards: [],
        reasons: [],
        width: 0,
        height: 0,
        topology: { columns: 5, rows: 3 },
      };
    },
    write: async () => {
      throw new Error('No approvals during inference');
    },
  };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(Page),
        ),
      ),
    );
  });
  try {
    await act(async () =>
      root.root
        .findByProps({ 'aria-label': 'Zdjęcia źródłowe' })
        .findByType('button')
        .props.onClick(),
    );
    assert.equal(
      root.root.findByProps({ 'aria-label': 'Model podglądu' }).props.value,
      '',
    );
    await act(async () => button(root, 'Pokaż wynik baseline').props.onClick());
    assert.equal(calls[0][2], undefined);
    await act(async () =>
      button(root, 'Odśwież dostępne modele').props.onClick(),
    );
    const selector = root.root.findByProps({ 'aria-label': 'Model podglądu' });
    assert.equal(selector.findAllByType('option').length, 2);
    assert.match(text(selector), /epoka 3/);
    await act(async () =>
      selector.props.onChange({ target: { value: run.id } }),
    );
    await act(async () => button(root, 'Pokaż wynik hybrydy').props.onClick());
    assert.equal(calls[1][2], run.id);
    assert.match(text(root.toJSON()), /bramka niekalibrowana/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('lost response keeps request and position, toast timeout does not clear retry; draft and ninth position stay', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  let clock = 0;
  t.mock.method(performance, 'now', () => clock);
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0), 'source:8': annotation(8) },
  });
  try {
    harness.failOnce();
    await act(async () =>
      button(harness.root, 'Zatwierdź tylko lokalizację').props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      1,
    );
    await act(async () => {
      clock += 4000;
      t.mock.timers.tick(250);
    });
    assert.equal(
      harness.root.root.findAllByProps({
        className: 'shared-toast shared-toast-error',
      }).length,
      0,
    );
    await act(async () =>
      button(
        harness.root,
        'Ponów identyczne żądanie: approve_location',
      ).props.onClick(),
    );
    assert.equal(harness.requests[0], harness.requests[1]);
    assert.equal(harness.requests[0].reviewed_all_nodes, false);
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    await act(async () => button(harness.root, 'Zapisz szkic').props.onClick());
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '9' } }),
    );
    await act(async () =>
      button(harness.root, 'Zatwierdź pełną siatkę').props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      9,
    );
    assert.doesNotMatch(text(harness.root.toJSON()), /Zatwierdzono 9 plansz/);
  } finally {
    await act(async () => harness.root.unmount());
  }
});
test('dirty navigation discards without confirmation or writes and conflict refresh still locks', async () => {
  const harness = await mount({
    revision: 1,
    annotations: { 'source:0': annotation(0) },
  });
  try {
    await act(async () =>
      button(harness.root, 'Nowa propozycja z narożników').props.onClick(),
    );
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '2' } }),
    );
    assert.equal(
      harness.root.root.findByProps({ type: 'number' }).props.value,
      2,
    );
    assert.equal(harness.requests.length, 0);
    await act(async () =>
      harness.root.root
        .findByProps({ type: 'number' })
        .props.onChange({ target: { value: '1' } }),
    );
    await act(async () =>
      button(harness.root, 'Nowa propozycja z narożników').props.onClick(),
    );
    let resolve;
    harness.setRead(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await act(async () =>
      button(harness.root, 'Odśwież po konflikcie').props.onClick(),
    );
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      true,
    );
    await act(async () =>
      resolve({ revision: 2, annotations: { 'source:0': annotation(0, 3) } }),
    );
    assert.equal(
      harness.root.root.findByProps({ 'aria-label': 'Edycja geometrii' }).props
        .disabled,
      false,
    );
    assert.equal(harness.previews.at(-1)[1], 3);
  } finally {
    await act(async () => harness.root.unmount());
  }
});

test('toast hover/focus pause, action isolation and dismissal keep the notification contract', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  let clock = 0;
  t.mock.method(performance, 'now', () => clock);
  let notify;
  let actions = 0;
  function Producer() {
    notify = useToast();
    return null;
  }
  let root;
  await act(async () => {
    root = create(
      React.createElement(ToastProvider, null, React.createElement(Producer)),
    );
  });
  try {
    await act(async () =>
      notify({
        kind: 'error',
        message: 'Retry failure',
        action: { label: 'Ponów', run: () => actions++ },
      }),
    );
    const toast = () =>
      root.root.findByProps({ className: 'shared-toast shared-toast-error' });
    assert.equal(toast().findByProps({ role: 'alert' }).props.role, 'alert');
    await act(async () => toast().props.onMouseEnter());
    await act(async () => {
      clock += 200000;
      t.mock.timers.tick(250);
    });
    assert.ok(toast());
    await act(async () =>
      toast().props.onMouseLeave({ currentTarget: { contains: () => true } }),
    );
    await act(async () => {
      clock += 200000;
      t.mock.timers.tick(250);
    });
    assert.ok(toast());
    let stopped = false;
    await act(async () =>
      button(root, 'Ponów').props.onClick({
        stopPropagation() {
          stopped = true;
        },
      }),
    );
    assert.equal(actions, 1);
    assert.equal(stopped, true);
    assert.ok(toast());
    await act(async () =>
      toast().props.onBlur({
        currentTarget: { matches: () => false, contains: () => false },
        relatedTarget: null,
      }),
    );
    document.hidden = true;
    await act(async () => {
      clock += 200000;
      t.mock.timers.tick(250);
    });
    assert.ok(toast());
    document.hidden = false;
    await act(async () => {
      clock += 4000;
      t.mock.timers.tick(250);
    });
    assert.equal(
      root.root.findAllByProps({ className: 'shared-toast shared-toast-error' })
        .length,
      0,
    );
    await act(async () => notify({ kind: 'success', message: 'Saved' }));
    await act(async () =>
      root.root
        .findByProps({ className: 'shared-toast shared-toast-success' })
        .props.onClick(),
    );
    assert.equal(
      root.root.findAllByProps({
        className: 'shared-toast shared-toast-success',
      }).length,
      0,
    );
  } finally {
    document.hidden = false;
    await act(async () => root.unmount());
  }
});

test('toast copies only original message, reports success after resolution and handles unavailable or rejected clipboard', async () => {
  let notify;
  function Producer() {
    notify = useToast();
    return null;
  }
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  let resolveCopy;
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      clipboard: {
        writeText(message) {
          copied.push(message);
          return new Promise((resolve) => {
            resolveCopy = resolve;
          });
        },
      },
    },
  });
  let root;
  await act(async () => {
    root = create(
      React.createElement(ToastProvider, null, React.createElement(Producer)),
    );
  });
  try {
    await act(async () =>
      notify({ kind: 'error', message: 'Original failure' }),
    );
    let stopped = false;
    await act(async () => {
      void button(root, 'Kopiuj').props.onClick({
        stopPropagation() {
          stopped = true;
        },
      });
    });
    assert.equal(stopped, true);
    assert.deepEqual(copied, ['Original failure']);
    assert.doesNotMatch(text(root.toJSON()), /Skopiowano/);
    assert.equal(button(root, 'Kopiuj').props.disabled, true);
    await act(async () => resolveCopy());
    assert.match(text(root.toJSON()), /Skopiowano/);
    navigator.clipboard.writeText = async (message) => {
      copied.push(message);
      throw new Error('denied');
    };
    await act(async () =>
      button(root, 'Kopiuj').props.onClick({ stopPropagation() {} }),
    );
    assert.doesNotMatch(text(root.toJSON()), /Skopiowano/);
    assert.match(text(root.toJSON()), /Nie udało się skopiować/);
    assert.deepEqual(copied, ['Original failure', 'Original failure']);
    delete navigator.clipboard;
    await act(async () =>
      button(root, 'Kopiuj').props.onClick({ stopPropagation() {} }),
    );
    assert.match(text(root.toJSON()), /Nie udało się skopiować/);
    assert.equal(
      root.root.findAllByProps({ className: 'shared-toast shared-toast-error' })
        .length,
      1,
    );
    assert.equal(button(root, 'Kopiuj').props.disabled, false);
  } finally {
    if (previous) Object.defineProperty(globalThis, 'navigator', previous);
    else delete globalThis.navigator;
    await act(async () => root.unmount());
  }
});

test('provider ignores an older response arriving after a successful mutation', async () => {
  let shared;
  function Observer() {
    shared = useAnnotations();
    return null;
  }
  globalThis.labApi = { read: async () => ({ revision: 1, annotations: {} }) };
  let root;
  await act(async () => {
    root = create(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AnnotationProvider,
          null,
          React.createElement(Observer),
        ),
      ),
    );
  });
  try {
    await act(async () =>
      shared.accept({
        revision: 9,
        annotations: { 'source:0': annotation(0) },
      }),
    );
    await act(async () => shared.accept({ revision: 2, annotations: {} }));
    assert.equal(shared.state.revision, 9);
    assert.ok(shared.state.annotations['source:0']);
  } finally {
    await act(async () => root.unmount());
  }
});
