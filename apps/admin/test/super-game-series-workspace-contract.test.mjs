import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspace = await readFile(
  new URL(
    '../src/features/super-games/super-game-series-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const catalog = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const navigation = await readFile(
  new URL('../src/features/catalog/admin-navigation-state.ts', import.meta.url),
  'utf8',
);

test('lists series with filters, a cursor page button and the undefined counter', () => {
  assert.match(workspace, /listSuperGameSeries\(gameId, seriesListQuery\(/);
  assert.doesNotMatch(workspace, /undefinedSeriesCountQuery/);
  assert.match(workspace, /undefinedSeriesCountLabel\(list\.counts\)/);
  assert.match(workspace, /seriesCountsCaption\(list\.counts\)/);
  assert.match(workspace, /data-testid="undefined-series-count"/);
  assert.match(workspace, /Kompletność/);
  assert.match(workspace, /Wiarygodność przebiegu/);
  assert.match(workspace, /COMPLETENESS_FILTER_OPTIONS/);
  assert.match(workspace, /RUN_VERIFICATION_FILTER_OPTIONS/);
  assert.match(workspace, /DEFINED_FILTER_OPTIONS/);
  assert.match(workspace, /Wczytaj kolejne/);
  assert.match(workspace, /list\.nextCursor/);
});

test('derives series on demand and explains a stale generation', () => {
  assert.match(workspace, /Przelicz serie/);
  assert.match(workspace, /api\s*\.deriveSuperGameSeries\(gameId\)/);
  assert.match(workspace, /deriveResultMessage\(result\.data\)/);
  assert.match(workspace, /superGameStateBanner\(generation\)/);
  assert.match(workspace, /getSuperGameSeriesState\(gameId\)/);
  assert.match(workspace, /SERIES_STATE_POLL_INTERVAL_MS/);
  assert.match(workspace, /window\.clearInterval/);
});

test('the series view has a carousel of positions with missing cards and retriggers', () => {
  assert.match(workspace, /aria-label="Karuzela pozycji serii"/);
  assert.match(workspace, /aria-label="Pozycje serii"/);
  assert.match(workspace, /data-testid="missing-card"/);
  assert.match(workspace, /missingCardLabel\(activeCard\)/);
  assert.match(workspace, /Retrigger/);
  assert.match(workspace, /Plansza wyzwalająca/);
  assert.match(workspace, /← Poprzednia/);
  assert.match(workspace, /Następna →/);
  assert.match(workspace, /Użyj ← \/ →/);
  assert.match(workspace, /Pokaż planszę z liniami/);
  assert.match(workspace, /BoardSearchBoardLinesModal/);
  assert.match(workspace, /boardSearchBoardViewUrl/);
});

test('marks the trigger symbol cells of the board', () => {
  assert.match(workspace, /triggerCellIndexes\(detail\.symbolCodes/);
  assert.match(workspace, /triggerSymbols\(symbols\)/);
  assert.match(workspace, /aria-label=\{`Układ symboli planszy #/);
  assert.match(workspace, /styles\.triggerCell/);
  assert.match(workspace, /cellPolygons/);
});

test('the super symbol select offers only ordinary symbols with digit labels', () => {
  assert.match(workspace, /ordinarySuperSymbols\(symbols\)/);
  assert.match(workspace, /ordinary\.map\(\(symbol, index\)/);
  assert.match(workspace, /superGameSeriesShortcutLabel\(index\)/);
  assert.match(workspace, /<kbd>1<\/kbd>–<kbd>9<\/kbd>, <kbd>0<\/kbd>/);
  assert.match(workspace, /Wyczyść symbol/);
  assert.match(workspace, /Zapisz \(Enter\)/);
  assert.match(workspace, /Anuluj \(Esc\)/);
  assert.match(
    workspace,
    /Zapis nie zmienia\s+kompletności ani wiarygodności przebiegu/,
  );
});

test('saves with the shown revision and never overwrites on a conflict', () => {
  assert.match(workspace, /beginSuperSymbolSave\(view, symbols\)/);
  assert.match(
    workspace,
    /setSuperGameSeriesSuperSymbol\(gameId, savedSeriesId/,
  );
  assert.match(workspace, /isSeriesRevisionConflict\(result\.error\)/);
  assert.match(workspace, /onOpenSeries\(applySuperSymbolConflict\)/);
  assert.match(workspace, /saveOperation\.current === operation/);
  assert.match(workspace, /state\.series\.id === savedSeriesId/);
  assert.match(workspace, /reloadList\(\);/);
  assert.match(workspace, /refreshRequested\.current = true/);
  assert.match(workspace, /applySuperSymbolFailure\(state, message\)/);
  assert.match(workspace, /applySuperSymbolSaved\(state, updated, symbols\)/);
});

test('shows three independent badges per series', () => {
  assert.match(workspace, /seriesBadges\(series, symbols\)/);
  assert.match(workspace, /data-badge=\{badge\.id\}/);
});

test('keyboard shortcuts skip text fields, the lines window and modifiers', () => {
  assert.match(workspace, /isSuperGameSeriesShortcutBlocked\(event\.target/);
  assert.match(workspace, /resolveSuperGameSeriesKeyboardCommand\(/);
  assert.match(workspace, /current\.linesOpen/);
  assert.match(workspace, /!event\.repeat/);
  assert.match(workspace, /event\.currentTarget\.blur\(\)/);
  assert.match(workspace, /window\.addEventListener\('keydown'/);
  assert.match(workspace, /window\.removeEventListener\('keydown'/);
});

test('the catalog shows the section only for games with a super game', () => {
  assert.match(catalog, /id: 'super-games'/);
  assert.match(catalog, /title: 'Supergry'/);
  assert.match(catalog, /isGameSectionAvailable\(section\.id, activeGame\)/);
  assert.match(catalog, /GAME_SECTION_OPTIONS\.map/);
  assert.match(catalog, /<SuperGameSeriesWorkspace/);
  assert.match(catalog, /seriesId=\{navigation\.seriesId\}/);
  assert.match(
    catalog,
    /isGameSectionAvailable\('super-games', loadedActive\)/,
  );
  assert.match(navigation, /'super-games'/);
  assert.match(navigation, /game\.superGameKind !== 'none'/);
});

test('uses the series from the URL parameter so that board search can link to it', () => {
  assert.match(navigation, /SUPER_GAME_SERIES_PARAMETER = 'series'/);
  assert.match(workspace, /listSuperGameSeriesBoards\(gameId, seriesId\)/);
  assert.match(workspace, /onSeriesChange/);
});
