import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/unreadable-board-reviews/unreadable-board-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('renders the whole topology and exposes both unreadable resolutions', () => {
  assert.match(source, /Weryfikacja symbolu na planszy/);
  assert.match(source, /Do ustalenia/);
  assert.match(source, /Wszystkie nieczytelne/);
  assert.match(source, /repeat\(\$\{detail\.gridColumns\}/);
  assert.match(source, /detail\.cells\.map/);
  assert.match(source, /kind: 'symbol'/);
  assert.match(source, /kind: 'unknown'/);
  assert.ok(
    /Ustaw \?/.test(source) || /UNKNOWN_SELECTION/.test(source),
    'the workspace must expose the unknown assignment',
  );
  assert.match(source, /Nieczytelny · poza treningiem/);
});

test('binds each decision to the exact crop revision and checksum', () => {
  assert.match(source, /expectedCropChecksumSha256: cell\.cropChecksumSha256/);
  assert.match(source, /expectedCropSampleId: cell\.cropSampleId/);
  assert.match(source, /expectedGeometryRevision: cell\.geometryRevision/);
  assert.match(source, /expectedRevision: cell\.revision/);
  assert.ok(
    /savingCell !== null/.test(source) || /savingBoard/.test(source),
    'the workspace must block overlapping cell or whole-board saves',
  );
});
