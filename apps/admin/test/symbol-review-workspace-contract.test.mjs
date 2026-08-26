import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/symbol-reviews/symbol-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const styles = await readFile(
  new URL(
    '../src/features/symbol-reviews/symbol-review-workspace.module.css',
    import.meta.url,
  ),
  'utf8',
);

test('provides browse-only game, symbol, state and unknown filters', () => {
  assert.match(source, /Weryfikacja symboli/);
  assert.match(source, /Nierozpoznany \(\?\)/);
  assert.match(source, /Zatwierdzone/);
  assert.match(source, /Oczekujące/);
  assert.doesNotMatch(source, /startSymbolCellReviewBulkOperation/);
  assert.doesNotMatch(source, /mark_grid_issue/);
});

test('uses lazy, checksum-bound assets with a local fallback per failed image', () => {
  assert.match(source, /symbolCellReviewAssetUrl/);
  assert.match(source, /item\.cropChecksumSha256/);
  assert.match(source, /loading="lazy"/);
  assert.match(source, /onError=\{\(\) => setImageFailed\(true\)\}/);
  assert.match(source, /Brak aktualnego cropa/);
});

test('keeps a bounded responsive page grid and no selection toolbar', () => {
  assert.match(source, /Po 60 cropów · w pamięci najwyżej 3 strony/);
  assert.match(source, /next_page_prefetched/);
  assert.match(styles, /repeat\(auto-fill, minmax\(144px, 1fr\)\)/);
  assert.doesNotMatch(source, /Zaznacz widoczną stronę/);
  assert.doesNotMatch(source, />Zmień symbol</);
});
