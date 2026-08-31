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
const previewSource = await readFile(
  new URL(
    '../src/features/symbol-reviews/symbol-review-virtual-previews.ts',
    import.meta.url,
  ),
  'utf8',
);

test('provides confirmable game, symbol, state, confidence and unknown filters', () => {
  assert.match(source, /Weryfikacja symboli/);
  assert.match(source, /Nierozpoznany \(\?\)/);
  assert.match(source, /Zatwierdzone/);
  assert.match(source, /Oczekujące/);
  assert.match(source, /Pewność predykcji/);
  assert.match(source, /Zatwierdź wybór/);
  assert.match(source, /Zmień wybór/);
  assert.match(source, /filtersConfirmed/);
  assert.match(styles, /\.filters fieldset \{[\s\S]*grid-column: 1 \/ span 3;/);
  assert.match(source, /state: 'pending'/);
  assert.match(source, /startSymbolReviewBulkOperation/);
  assert.match(source, /mark_grid_issue/);
  assert.match(source, /mark_unreadable/);
});

test('uses checksum-bound stable atlases for legacy and virtual previews', () => {
  assert.match(previewSource, /item\.cropChecksumSha256/);
  assert.match(previewSource, /createSymbolCellPreviewBatch/);
  assert.doesNotMatch(source, /symbolCellReviewAssetUrl/);
  assert.doesNotMatch(source, /<img/);
  assert.match(source, /loadSymbolReviewPreviewAtlases/);
  assert.match(source, /SymbolReviewVirtualGrid/);
  assert.match(source, /virtualPreviewTiles/);
});

test('keeps a three-page metadata window with virtual cards and background bulk controls', () => {
  assert.doesNotMatch(source, /IntersectionObserver/);
  assert.match(source, /page_prefetched/);
  assert.match(source, /findCachedSymbolReviewPage/);
  assert.match(source, /pagePositionRef/);
  assert.match(source, /maks\. \$\{filters\.pageSize\} symboli/);
  assert.match(source, /Poprzednia strona/);
  assert.match(source, /Następna strona/);
  assert.match(styles, /width: 100px/);
  assert.match(styles, /height: 100px/);
  assert.match(source, /Zaznacz stronę/);
  assert.match(source, /Zaznacz wyniki filtra/);
  assert.match(
    source,
    /disabled=\{interactionBusy \|\| pendingCellIds\.has\(item\.id\)\}/,
  );
  assert.match(source, />\s*Zła siatka\s*</);
  assert.match(source, /Nieczytelny symbol/);
  assert.match(source, /Zmiana filtra wyczyści bieżące zaznaczenie/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /window\.setTimeout/);
  assert.match(source, /activeOperations/);
  assert.match(source, /Operacje masowe w tle/);
  assert.match(source, /Operacja została przekazana do przetwarzania w tle/);
  assert.doesNotMatch(source, /pageRefreshRevision/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /Edytuj siatkę/);
  assert.match(styles, /position: sticky/);
  assert.match(styles, /\.pagination/);
});

test('keeps an explicit selection across page navigation and tracks every submitted crop', () => {
  const movePageSource = source.slice(
    source.indexOf('const movePage'),
    source.indexOf('async function prepareProjection'),
  );
  assert.doesNotMatch(
    movePageSource,
    /setSelection\(createEmptySymbolReviewSelection\(\)\)/,
  );
  assert.doesNotMatch(movePageSource, /setHiddenCellIds\(new Set\(\)\)/);
  assert.match(source, /Object\.keys\(selection\.targetsById\)/);
});

test('shows only crop thumbnails and exposes durable mutation feedback', () => {
  assert.doesNotMatch(source, /className=\{styles\.cardBody\}/);
  assert.match(source, /Zapisywanie zmiany/);
  assert.match(source, /pendingCellIds/);
  assert.match(source, /hiddenCellIds/);
  assert.match(styles, /\.cardPending/);
  assert.match(styles, /\.cardBadge/);
  assert.match(source, /item\.qualityIssue === 'unreadable'/);
  assert.match(source, /item\.cropApprovalState === 'changed_since_approval'/);
  assert.match(styles, /symbolReviewSpin/);
  assert.match(source, /applySingleSymbolReviewDecision/);
  assert.match(source, /Symbol został zmieniony/);
  assert.match(styles, /\.toastSuccess/);
  assert.match(styles, /bottom: 50px/);
  assert.match(styles, /left: 50px/);
  assert.match(styles, /\.operationLoader/);
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
  assert.match(source, /currentPageRange\.start/);
  assert.match(source, /currentPageRange\.end/);
  assert.match(source, /zakres/);
  assert.match(source, /filteredSymbolReviewCount/);
});

test('renders metadata before independent revision-bound counts finish', () => {
  assert.match(source, /loadSymbolReviewCounts/);
  assert.match(source, /countsRequestId/);
  assert.match(source, /countsCatalogRevision/);
  assert.match(source, /liczniki niedostępne/);
  assert.doesNotMatch(source, /currentPage\.counts/);
});
