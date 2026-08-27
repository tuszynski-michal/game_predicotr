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

test('provides game, symbol, state and unknown filters', () => {
  assert.match(source, /Weryfikacja symboli/);
  assert.match(source, /Nierozpoznany \(\?\)/);
  assert.match(source, /Zatwierdzone/);
  assert.match(source, /Oczekujące/);
  assert.match(source, /startSymbolReviewBulkOperation/);
  assert.match(source, /mark_grid_issue/);
});

test('uses lazy, checksum-bound assets with a local fallback per failed image', () => {
  assert.match(source, /symbolCellReviewAssetUrl/);
  assert.match(source, /item\.cropChecksumSha256/);
  assert.match(source, /loading="lazy"/);
  assert.match(source, /onError=\{\(\) => setImageFailed\(true\)\}/);
  assert.match(source, /Brak aktualnego cropa/);
});

test('keeps a bounded responsive page grid with safe bulk review controls', () => {
  assert.match(source, /IntersectionObserver/);
  assert.match(source, /maks\. 180 cropów/);
  assert.match(source, /topSentinelRef/);
  assert.match(source, /bottomSentinelRef/);
  assert.match(styles, /repeat\(auto-fill, minmax\(144px, 1fr\)\)/);
  assert.match(source, /Zaznacz widoczną stronę/);
  assert.match(source, /Zaznacz wszystkie wyniki filtra/);
  assert.match(source, /Oznacz złą siatkę/);
  assert.match(source, /Zmiana filtra wyczyści bieżące zaznaczenie/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /window\.setTimeout/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /Edytuj siatkę/);
  assert.match(styles, /position: sticky/);
  assert.match(styles, /overflow-y: auto/);
});

test('shows durable projection preparation states and progress', () => {
  assert.match(source, /Przygotuj weryfikację symboli/);
  assert.match(source, /Wznów przygotowanie/);
  assert.match(source, /Uzupełnij brakujące symbole/);
  assert.match(source, /processedBoardCount/);
  assert.match(source, /persistedCellCount/);
  assert.match(source, /activeJobId/);
});
