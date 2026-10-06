import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { NeuralSourceBindingPanel } =
  await import('../src/features/imports/neural-source-binding-panel.tsx');
after(() => dom.window.close());
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 20.125 + (i % 6) * 20,
  y: 30.375 + Math.floor(i / 6) * 20,
}));
const proposal = {
  contractVersion: 'neural-grid-proposal-v1',
  gameId: 'g',
  sourceSelectionId: 's',
  sourceChecksumSha256: 'a'.repeat(64),
  sourceWidth: 600,
  sourceHeight: 400,
  originalRange: { sequenceRangeStart: 499996, sequenceRangeEnd: 500004 },
  engineSnapshot: { expectedLayoutCount: 500000, model: {} },
  proposalChecksumSha256: 'b'.repeat(64),
  detections: ['a', 'b', 'd', 'e', 'extra'].map((detectionId) => ({
    detectionId,
    structurallyValid: true,
    latticeNodes: nodes,
    score: 0.9,
    reasonCodes: [],
    cellQuads: [],
    cellVisibility: Array(15).fill('full'),
  })),
};
const source = {
  sourceRelativePath: 'seq_499996-500004.jpg',
  neuralProposal: proposal,
  neuralProposalBinding: null,
  existingOverrideRevision: 0,
};
const button = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);
async function change(element, value) {
  await act(async () => {
    if (element.tagName === 'INPUT')
      Object.getOwnPropertyDescriptor(
        dom.window.HTMLInputElement.prototype,
        'value',
      ).set.call(element, value);
    else element.value = value;
    element.dispatchEvent(
      new Event(element.tagName === 'INPUT' ? 'input' : 'change', {
        bubbles: true,
      }),
    );
  });
}
async function loaded() {
  await act(async () =>
    document.querySelector('svg image').dispatchEvent(new Event('load')),
  );
}
test('explicit corrected five-slot range, missing middle and rejected extra survive restart and lost response', async () => {
  localStorage.clear();
  const commands = [];
  let lost = true,
    saved = 0;
  const props = {
    api: {
      createBrowserPageGeometryOverride: async (id, command) => {
        commands.push(structuredClone(command));
        if (lost) {
          lost = false;
          throw Error('lost');
        }
        return { data: { revision: 1 } };
      },
    },
    gameId: 'g',
    uploadId: 'u',
    source,
    imageUrl: 'http://localhost/fixture',
    preflightJobId: 'preflight',
    manifestChecksumSha256: 'c'.repeat(64),
    onSaved: () => saved++,
    onRefresh: async () => {},
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(NeuralSourceBindingPanel, props)),
  );
  assert.match(document.body.textContent, /Wczytywanie zdjęcia/);
  assert.equal(button('Zapisz przypisanie plansz').disabled, true);
  await loaded();
  await change(
    document.querySelector('[aria-label="Ostatnia plansza"]'),
    '500000',
  );
  await act(async () =>
    [...document.querySelectorAll('label')]
      .find((l) => l.textContent.includes('Potwierdzam numery'))
      .querySelector('input')
      .click(),
  );
  for (const [i, value] of ['0', '1', '3', '4', 'ignore'].entries())
    await change(
      document.querySelector(`[aria-label="Przypisanie propozycji ${i + 1}"]`),
      value,
    );
  await act(async () =>
    [...document.querySelectorAll('label')]
      .find((l) => l.textContent.includes('Plansza 499998: potwierdzam brak'))
      .querySelector('input')
      .click(),
  );
  assert.equal(button('Zapisz przypisanie plansz').disabled, false);
  await act(async () => button('Zapisz przypisanie plansz').click());
  assert.equal(commands.length, 1);
  assert.deepEqual(commands[0].finalQuads, []);
  assert.equal(commands[0].geometryPreflightJobId, 'preflight');
  assert.equal(commands[0].geometryManifestChecksumSha256, 'c'.repeat(64));
  assert.equal(
    commands[0].neuralProposalBinding.confirmedRange.sequenceRangeEnd,
    500000,
  );
  assert.deepEqual(
    commands[0].neuralProposalBinding.missingPositionIndexes,
    [2],
  );
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(NeuralSourceBindingPanel, props)),
  );
  await loaded();
  assert.equal(
    document.querySelector('[aria-label="Ostatnia plansza"]').value,
    '500000',
  );
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => button('Ponów ten sam zapis').click());
  assert.deepEqual(commands[1], commands[0]);
  assert.equal(saved, 1);
  await act(async () => root.unmount());
});
test('empty proposal stays visible; source load error blocks all writes', async () => {
  localStorage.clear();
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(NeuralSourceBindingPanel, {
        api: {
          createBrowserPageGeometryOverride: () => assert.fail('no write'),
        },
        gameId: 'g',
        uploadId: 'u',
        source: { ...source, neuralProposal: { ...proposal, detections: [] } },
        imageUrl: 'bad',
        preflightJobId: 'p',
        manifestChecksumSha256: 'm',
        onSaved: () => {},
        onRefresh: async () => {},
      }),
    ),
  );
  assert.match(document.body.textContent, /Sieć nie znalazła/);
  await act(async () =>
    document.querySelector('svg image').dispatchEvent(new Event('error')),
  );
  assert.match(document.body.textContent, /Nie udało się wczytać zdjęcia/);
  assert.equal(button('Zapisz przypisanie plansz').disabled, true);
  await act(async () => root.unmount());
});

test('a changed immutable proposal blocks restoring or writing the earlier draft', async () => {
  localStorage.clear();
  const props = {
    api: {
      createBrowserPageGeometryOverride: () =>
        assert.fail('stale draft must not write'),
    },
    gameId: 'g',
    uploadId: 'u',
    source,
    imageUrl: 'fixture',
    preflightJobId: 'p',
    manifestChecksumSha256: 'm',
    onSaved: () => {},
    onRefresh: async () => {},
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(NeuralSourceBindingPanel, props)),
  );
  await change(
    document.querySelector('[aria-label="Ostatnia plansza"]'),
    '500000',
  );
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(NeuralSourceBindingPanel, {
        ...props,
        source: {
          ...source,
          neuralProposal: {
            ...proposal,
            proposalChecksumSha256: 'd'.repeat(64),
          },
        },
      }),
    ),
  );
  await loaded();
  assert.match(document.body.textContent, /Szkic ma inną propozycję/);
  assert.equal(button('Zapisz przypisanie plansz').disabled, true);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => root.unmount());
});
