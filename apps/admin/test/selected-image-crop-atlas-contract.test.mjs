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
const styles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('local review atlases contain at most one hundred deterministic thumbnails', () => {
  assert.match(atlas, /ATLAS_BATCH_SIZE = 100/u);
  assert.match(atlas, /outputChecksumSha256/u);
  assert.match(atlas, /image\/webp/u);
  assert.match(atlas, /THUMBNAIL_WIDTH = 144/u);
  assert.match(atlas, /THUMBNAIL_HEIGHT = 96/u);
  assert.match(atlas, /selected-image-crop-atlas-webp-v2/u);
  assert.match(atlas, /image\/webp', 0\.58/u);
  assert.match(atlas, /SELECTED_IMAGE_CROP_ATLAS_DIRECTORY/u);
  assert.match(atlas, /await yieldToBrowser\(\)/u);
});

test('larger crop thumbnails stay in one horizontally scrollable row', () => {
  assert.match(
    styles,
    /\.selectedImageCropGrid\s*\{[\s\S]*?display:\s*flex;[\s\S]*?overflow-x:\s*auto;/u,
  );
  assert.match(
    styles,
    /\.selectedImageCropTile\s*\{[\s\S]*?flex:\s*0 0 144px;/u,
  );
  assert.match(
    styles,
    /\.selectedImageCropTilePlaceholder\s*\{[\s\S]*?width:\s*144px;[\s\S]*?height:\s*96px;/u,
  );
});

test('crop worker is recycled and has an explicit unsupported-browser fallback', () => {
  assert.match(worker, /typeof Worker === 'undefined'/u);
  assert.match(worker, /typeof OffscreenCanvas === 'undefined'/u);
  assert.match(worker, /requestCount >= 128/u);
  assert.match(worker, /activeWorker\?\.terminate\(\)/u);
});
