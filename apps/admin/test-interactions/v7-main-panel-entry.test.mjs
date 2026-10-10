import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { renderToString } from 'react-dom/server';

const mainUrl =
  'http://127.0.0.1:3000/?game=main-game&section=imports&workspace=semi-automatic-image-selection';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: mainUrl });
for (const key of ['window', 'document', 'HTMLElement', 'Element', 'Event']) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(globalThis, 'indexedDB', {
  configurable: true,
  value: undefined,
});
const originalPilotOrigin = process.env.NEXT_PUBLIC_V7_SELECTION_PILOT_ORIGIN;
delete process.env.NEXT_PUBLIC_V7_SELECTION_PILOT_ORIGIN;
const { createRoot } = await import('react-dom/client');
const { SemiAutomaticSelectionWorkspace } =
  await import('../src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx');
after(() => {
  if (originalPilotOrigin === undefined) {
    delete process.env.NEXT_PUBLIC_V7_SELECTION_PILOT_ORIGIN;
  } else {
    process.env.NEXT_PUBLIC_V7_SELECTION_PILOT_ORIGIN = originalPilotOrigin;
  }
  dom.window.close();
});

async function withWorkspace(options, inspect) {
  dom.reconfigure({ url: options.url ?? mainUrl });
  dom.window.localStorage.clear();
  const calls = [];
  if (options.run) {
    dom.window.localStorage.setItem(
      'game-predictor:semi-automatic-selection:last-run',
      options.run.id,
    );
  }
  const client = {
    async listSemiAutomaticImageSelections(mode, offset, limit) {
      assert.deepEqual([mode, offset, limit], ['v7_selection', 0, 100]);
      calls.push('saved-runs');
      return { data: { items: [] } };
    },
    async getSemiAutomaticImageSelectionCapabilities() {
      calls.push('capabilities');
      return {
        data: {
          enabled: options.enabled ?? true,
          fullRangeSize: 9,
          rangeConvention: 'seq-inclusive-v1',
          v7: {
            startEnabled: options.active ?? false,
            reason: 'holdout blocked',
          },
        },
      };
    },
    async getSemiAutomaticImageSelection(id) {
      calls.push(`restore:${id}`);
      return { data: options.run };
    },
    async listSemiAutomaticImageSelectionSources() {
      calls.push('sources');
      return { data: { items: [], nextAfterSourceIndex: null } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => {
      root.render(
        React.createElement(SemiAutomaticSelectionWorkspace, {
          client,
          apiBaseUrl: 'http://127.0.0.1:8000',
        }),
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await inspect(document.getElementById('root'), calls);
  } finally {
    await act(async () => root.unmount());
    dom.window.localStorage.clear();
  }
}

test('blocked main offers pilot navigation without source/create/approve calls', async () => {
  await withWorkspace({}, async (container, calls) => {
    const link = container.querySelector('a');
    assert.equal(link?.textContent.trim(), 'Otwórz półautomat V7');
    assert.equal(
      link.href,
      'http://127.0.0.1:3020/?workspace=semi-automatic-image-selection',
    );
    assert.equal(
      container.querySelector('[aria-label="Konfiguracja runu"]'),
      null,
    );
    assert.equal(container.querySelector('[role="alert"]'), null);
    assert.ok(
      [...container.querySelectorAll('button')].some(
        (button) => button.textContent.trim() === 'Wybierz katalog nadrzędny',
      ),
    );
    const click = new dom.window.MouseEvent('click', {
      bubbles: true,
      cancelable: true,
    });
    link.addEventListener('click', (event) => event.preventDefault(), {
      once: true,
    });
    await act(async () => link.dispatchEvent(click));
    assert.deepEqual(calls, ['saved-runs', 'capabilities']);
  });
});

test('active V7 keeps the source picker and original workflow', async () => {
  await withWorkspace({ active: true }, (container, calls) => {
    assert.equal(container.querySelector('a'), null);
    assert.ok(container.querySelector('[aria-label="Konfiguracja runu"]'));
    const picker = [...container.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === 'Wybierz katalog źródłowy',
    );
    assert.equal(picker.disabled, false);
    assert.deepEqual(calls, ['saved-runs', 'capabilities']);
  });
});

test('server flag-off keeps the disabled workflow and cannot offer a pilot bypass', async () => {
  await withWorkspace({ enabled: false }, (container) => {
    assert.equal(container.querySelector('a'), null);
    assert.match(
      container.textContent,
      /wyłączona przez lokalną flagę serwera/,
    );
    const picker = [...container.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === 'Wybierz katalog źródłowy',
    );
    assert.equal(picker.disabled, true);
  });
});

test('non-local main keeps its existing blocked form', async () => {
  await withWorkspace({ url: 'http://192.168.1.2:3000' }, (container) => {
    assert.equal(container.querySelector('a'), null);
    assert.ok(container.querySelector('[aria-label="Konfiguracja runu"]'));
    assert.match(container.textContent, /V7 jest zablokowane: holdout blocked/);
  });
});

test('existing main run retains its source restoration and progress alongside the link', async () => {
  const run = {
    id: 'existing-main-run',
    firstSequenceNumber: 1,
    lastSequenceNumber: 18,
    direction: 'ascending',
    workflowMode: 'selection',
    status: 'completed',
    source: { sourceCount: 2 },
    counters: {},
    job: {
      status: 'completed',
      inputPayload: {},
      progress: { stage: 'completed', current: 2, total: 2, unit: 'sources' },
    },
  };
  await withWorkspace({ run }, (container, calls) => {
    assert.ok(container.querySelector('a'));
    assert.ok(container.querySelector('[aria-label="Konfiguracja runu"]'));
    assert.ok(
      container.querySelector('[aria-label="Postęp analizy zakresów"]'),
    );
    assert.deepEqual(calls, [
      'saved-runs',
      'capabilities',
      'restore:existing-main-run',
      'sources',
    ]);
  });
});

test('entry survives a fresh mount and server rendering needs no browser origin', async () => {
  for (let index = 0; index < 2; index += 1) {
    await withWorkspace({}, (container) => {
      assert.equal(
        container.querySelector('a')?.href,
        'http://127.0.0.1:3020/?workspace=semi-automatic-image-selection',
      );
    });
  }
  dom.window.localStorage.clear();
  const windowDescriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    'window',
  );
  delete globalThis.window;
  let html;
  try {
    html = renderToString(
      React.createElement(SemiAutomaticSelectionWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client: {},
      }),
    );
  } finally {
    Object.defineProperty(globalThis, 'window', windowDescriptor);
  }
  assert.doesNotMatch(html, /Otwórz półautomat V7/);
  assert.match(html, /Sprawdzanie dostępności/);
});
