import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PreviewCache,
  PREVIEW_BITMAP_BUDGET,
} from '../src/renderer/preview-cache.ts';
const tick = async () => {
  for (let n = 0; n < 8; n++) await Promise.resolve();
};
function fixture(count = 12) {
  const images = Array.from({ length: count }, (_, n) => ({
    id: String(n),
    url: `photo:${n}`,
    relativePath: `${n}.jpg`,
  }));
  const source = { id: 'source1', images };
  const created = [];
  const cache = new PreviewCache(() => {
    const image = {
      naturalWidth: 10,
      naturalHeight: 10,
      removed: false,
      remove() {
        this.removed = true;
      },
      removeAttribute() {
        this.src = '';
      },
      decode() {
        return new Promise((resolve, reject) => {
          this.resolve = resolve;
          this.reject = reject;
        });
      },
    };
    created.push(image);
    return image;
  });
  return { source, images, created, cache };
}
test('active first; same decoded object on hit; one prefetch decode and nearest window', async () => {
  const { source, images, created, cache } = fixture();
  const active = cache.activate(source, images[5]);
  assert.deepEqual(
    created.map((i) => i.src),
    ['photo:5'],
  );
  created[0].resolve();
  const displayed = await active;
  assert.equal(displayed, created[0]);
  assert.equal(created.length, 2);
  await tick();
  assert.equal(created.length, 2);
  for (let n = 1; n < 7; n++) {
    created[n].resolve();
    await tick();
  }
  assert.equal(cache.size, 7);
  assert.deepEqual(
    created.map((i) => i.src),
    [
      'photo:5',
      'photo:6',
      'photo:4',
      'photo:7',
      'photo:3',
      'photo:8',
      'photo:2',
    ],
  );
  assert.equal(await cache.activate(source, images[6]), created[1]);
  // One new neighbour at the edge, no new object for the hit.
  assert.equal(created.filter((i) => i.src === 'photo:6').length, 1);
  assert.ok(cache.size <= 7);
  cache.clear();
  assert.equal(cache.size, 0);
  assert.ok(created.every((i) => i.src === ''));
});
test('late active decode and new source with same image ids cannot reuse old images', async () => {
  const { source, images, created, cache } = fixture();
  const old = cache.activate(source, images[0]);
  const rejected = assert.rejects(old, /invalidated|superseded/);
  const changed = cache.activate({ ...source, id: 'source2' }, images[0]);
  created[0].resolve();
  await rejected;
  assert.equal(created[0].src, '');
  created[1].resolve();
  assert.equal(await changed, created[1]);
  cache.clear();
});
test('decode failure is not a hit; retry loads a fresh object', async () => {
  const { source, images, created, cache } = fixture();
  const failed = cache.activate(source, images[0]);
  created[0].reject(new Error('broken JPEG'));
  await assert.rejects(failed, /broken JPEG/);
  assert.equal(cache.size, 0);
  const retry = cache.activate(source, images[0]);
  created[1].resolve();
  assert.equal(await retry, created[1]);
  cache.clear();
});
test('large active is sole budget exception and disables prefetch', async () => {
  const { source, images, created, cache } = fixture();
  const active = cache.activate(source, images[0]);
  created[0].naturalWidth = 10000;
  created[0].naturalHeight = 10000;
  created[0].resolve();
  await active;
  await tick();
  assert.equal(cache.size, 1);
  assert.ok(cache.estimatedBytes > PREVIEW_BITMAP_BUDGET);
  assert.equal(created.length, 1);
  cache.clear();
});
test('unknown-size neighbour is evicted after decode; no infinite prefetch retry', async () => {
  const { source, images, created, cache } = fixture();
  const active = cache.activate(source, images[0]);
  created[0].resolve();
  await active;
  created[1].naturalWidth = 10000;
  created[1].naturalHeight = 10000;
  created[1].resolve();
  await tick();
  assert.equal(cache.size, 1);
  assert.ok(cache.estimatedBytes <= PREVIEW_BITMAP_BUDGET);
  assert.equal(created.length, 2);
  cache.clear();
});
test('fast reversal reuses pending active; superseded response is rejected', async () => {
  const { source, images, created, cache } = fixture();
  const first = cache.activate(source, images[0]);
  const firstRejected = assert.rejects(first, /superseded/);
  const second = cache.activate(source, images[1]);
  const secondRejected = assert.rejects(second, /superseded/);
  const back = cache.activate(source, images[0]);
  created[1].resolve();
  await secondRejected;
  created[0].resolve();
  await firstRejected;
  assert.equal(await back, created[0]);
  cache.clear();
});

test('new active bypasses a held prefetch while neighbours remain serial', async () => {
  const { source, images, created, cache } = fixture();
  const first = cache.activate(source, images[0]);
  created[0].resolve();
  await first;
  assert.equal(created[1].src, 'photo:1');
  const next = cache.activate(source, images[3]);
  assert.equal(created[2].src, 'photo:3');
  created[2].resolve();
  await next;
  await tick();
  assert.equal(created.length, 3); // No second prefetch while neighbour 1 is held.
  created[1].resolve();
  await tick();
  assert.equal(created[3].src, 'photo:4');
  cache.clear();
});
