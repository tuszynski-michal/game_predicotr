import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import ts from 'typescript';
import React from 'react';
import { act, create } from 'react-test-renderer';

// Isolated UI harness: real React components, transport replaced before import.
const apiUrl = new URL(
  '../../../packages/vision-lab-api-client/src/index.ts',
  import.meta.url,
).href;
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      const url = new URL(specifier, context.parentURL);
      for (const extension of ['', '.ts', '.tsx']) {
        const candidate = new URL(url.href + extension);
        if (existsSync(candidate))
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
          'export const assetUrl = (id) => id; export const readAnnotations = (...args) => globalThis.labApi.read(...args); export const writeAnnotation = (...args) => globalThis.labApi.write(...args); export const writePhotoReview = (...args) => globalThis.labApi.review(...args); export const previewGeometry = (...args) => globalThis.labApi.preview(...args); export const listSources = (...args) => globalThis.labApi.list(...args); export const detectGeometry = async () => ({}); export const writeFamily = async () => ({}); export const backupAnnotations = async () => ({}); export const annotationTimings = async () => [];',
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
const { AnnotationProvider, useAnnotations } =
  await import('../src/components/annotation-context.tsx');
const { default: Page } = await import('../src/app/page.tsx');
const { ToastProvider, useToast } =
  await import('../../../packages/ui/src/toasts.tsx');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = {
  addEventListener(type) {
    assert.notEqual(type, 'beforeunload');
  },
  removeEventListener() {},
  confirm() {
    throw new Error('Browser confirmation is forbidden in lab workflow');
  },
};
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
  typeof node === 'string' ? node : (node.children ?? []).map(text).join('');
function button(root, label) {
  return root.root.findAllByType('button').find((node) => text(node) === label);
}
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
    const close = harness.root.root
      .findAllByType('button')
      .find((node) =>
        node.props['aria-label']?.startsWith('Zamknij: Decyzja przeglądu'),
      );
    await act(async () => close.props.onClick({ stopPropagation() {} }));
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
test('lost response keeps request and position, toast dismissal does not clear retry; draft and ninth position stay', async () => {
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
    const close = harness.root.root
      .findAllByType('button')
      .find((node) =>
        node.props['aria-label']?.startsWith('Zamknij: Zapis niepotwierdzony'),
      );
    await act(async () => close.props.onClick({ stopPropagation() {} }));
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
      clock += 180001;
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
