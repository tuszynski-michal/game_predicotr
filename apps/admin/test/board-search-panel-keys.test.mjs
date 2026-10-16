import assert from 'node:assert/strict';
import test from 'node:test';
import {
  loadPanelKeys,
  storePanelKeys,
  panelShareUrl,
} from '../src/features/sharing/board-search-panel-keys.ts';
const panel = '11111111-1111-4111-8111-111111111111';
const key = {
  linkKey: 'a'.repeat(43),
  expiresAt: new Date(Date.now() + 3600000).toISOString(),
};

test('local key survives a fresh cache read and a new tunnel origin without extending expiry', () => {
  const memory = new Map();
  const storage = {
    getItem: (id) => memory.get(id) ?? null,
    setItem: (id, value) => memory.set(id, value),
  };
  assert.equal(storePanelKeys({ [panel]: key }, storage), true);
  const restored = loadPanelKeys(storage);
  assert.deepEqual(restored, { [panel]: key });
  assert.equal(
    panelShareUrl(
      `https://new.trycloudflare.com/board-search-panel?share=${panel}`,
      restored[panel],
    ),
    `https://new.trycloudflare.com/board-search-panel?share=${panel}#key=${key.linkKey}`,
  );
  assert.equal(panelShareUrl('https://new.trycloudflare.com', undefined), null);
  assert.deepEqual(loadPanelKeys(storage, Date.parse(key.expiresAt)), {});
});

test('unavailable or malformed storage does not fabricate a key', () => {
  assert.deepEqual(loadPanelKeys({ getItem: () => '{' }), {});
  assert.deepEqual(
    loadPanelKeys({ getItem: () => '{"__proto__":{"linkKey":"abc"}}' }),
    {},
  );
  assert.equal(
    storePanelKeys(
      {},
      {
        setItem: () => {
          throw new Error('blocked');
        },
      },
    ),
    false,
  );
});
