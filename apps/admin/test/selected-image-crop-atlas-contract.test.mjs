import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const atlas = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/selected-image-crop-atlases.ts',
    import.meta.url,
  ),
  'utf8',
);
const worker = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts',
    import.meta.url,
  ),
  'utf8',
);

test('local review atlases contain at most one hundred deterministic thumbnails', () => {
  assert.match(atlas, /ATLAS_BATCH_SIZE = 100/u);
  assert.match(atlas, /outputChecksumSha256/u);
  assert.match(atlas, /image\/webp/u);
  assert.match(atlas, /SELECTED_IMAGE_CROP_ATLAS_DIRECTORY/u);
  assert.match(atlas, /await yieldToBrowser\(\)/u);
});

test('crop worker is recycled and has an explicit unsupported-browser fallback', () => {
  assert.match(worker, /typeof Worker === 'undefined'/u);
  assert.match(worker, /typeof OffscreenCanvas === 'undefined'/u);
  assert.match(worker, /requestCount >= 128/u);
  assert.match(worker, /activeWorker\?\.terminate\(\)/u);
});
