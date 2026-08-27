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
  assert.match(source, /state: 'pending'/);
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

test('keeps one bounded five-hundred-item page with safe bulk review controls', () => {
  assert.doesNotMatch(source, /IntersectionObserver/);
  assert.doesNotMatch(source, /prefetchingCursorRef/);
  assert.match(source, /pagePositionRef/);
  assert.match(source, /maks\. 500 symboli/);
  assert.match(source, /Poprzednia strona/);
  assert.match(source, /Następna strona/);
  assert.match(styles, /repeat\(auto-fill, 100px\)/);
  assert.match(styles, /width: 100px/);
  assert.match(styles, /height: 100px/);
  assert.match(source, /Zaznacz całą stronę/);
  assert.doesNotMatch(source, /Zaznacz wszystkie wyniki filtra/);
  assert.match(source, /disabled=\{interactionBusy\}/);
  assert.match(source, /Oznacz złą siatkę/);
  assert.match(source, /Zmiana filtra wyczyści bieżące zaznaczenie/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /window\.setTimeout/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /Edytuj siatkę/);
  assert.match(styles, /position: sticky/);
  assert.match(styles, /\.pagination/);
});

test('shows only crop thumbnails and exposes durable mutation feedback', () => {
  assert.doesNotMatch(source, /className=\{styles\.cardBody\}/);
  assert.match(source, /Zapisywanie zmiany/);
  assert.match(source, /pendingCellIds/);
  assert.match(source, /hiddenCellIds/);
  assert.match(styles, /\.cardPending/);
  assert.match(styles, /symbolReviewSpin/);
  assert.match(source, /applySingleSymbolReviewDecision/);
  assert.match(source, /Symbol został zmieniony/);
  assert.match(styles, /\.toastSuccess/);
});

test('shows durable projection preparation states and progress', () => {
  assert.match(source, /Przygotuj weryfikację symboli/);
  assert.match(source, /Wznów przygotowanie/);
  assert.match(source, /Uzupełnij brakujące symbole/);
  assert.match(source, /Uzupełnianie oczekuje w kolejce/);
  assert.match(source, /processedBoardCount/);
  assert.match(source, /persistedCellCount/);
  assert.match(source, /activeJobId/);
  assert.match(source, /Strona \{currentPageNumber\}/);
  assert.match(source, /filteredSymbolReviewCount/);
});
