import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panelSource = await readFile(
  new URL(
    '../src/features/imports/image-folder-import-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);
const actionsSource = await readFile(
  new URL(
    '../src/features/imports/image-folder-import-actions.ts',
    import.meta.url,
  ),
  'utf8',
);
const globalStyles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);
const workspaceSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const guardResolutionSource = await readFile(
  new URL(
    '../src/features/imports/geometry-guard-resolution-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('a replacement recovers its preflight and opens geometry correction when ready', () => {
  assert.match(panelSource, /replacementPreviewStorageKey/);
  assert.match(panelSource, /recoverReplacementPreflight/);
  assert.match(panelSource, /focusSourceChecksumSha256=\{/);
  assert.match(panelSource, /<details open=\{replacementPreview\?\.uploadId === ready\.uploadId\}>/);
});

test('a new replacement stays editable until the operator starts preflight', () => {
  const replacementFlow = panelSource.slice(
    panelSource.indexOf('async function handlePageGeometrySourceReplaced'),
    panelSource.indexOf('async function retryGeometryPreflight'),
  );
  assert.doesNotMatch(replacementFlow, /startBrowserPageGeometryPreflight/);
  assert.match(panelSource, /initialReplacementSource=\{replacementPreview\.source\}/);
  assert.match(panelSource, /preflightJobId=\{`replacement-draft:/);
  assert.match(panelSource, /Po zapisaniu korekty uruchom preflight przyciskiem powyżej/);
  assert.match(panelSource, /onDraftSaved=\{markReplacementDraftSaved\}/);
  assert.match(panelSource, /replacementPreview\.saved/);
});

test('distinguishes the active import operation from a disabled prerequisite', () => {
  assert.match(panelSource, /type ImportAction =/);
  assert.match(panelSource, /activeAction === 'choose-folder'/);
  assert.doesNotMatch(panelSource, /activeAction === 'start-import'/);
  assert.match(panelSource, /activeAction === 'refresh-status'/);
  assert.match(panelSource, /activeAction === 'reprocess-import'/);
  assert.match(panelSource, /finally \{\s*setActiveAction\(null\)/);
  assert.match(globalStyles, /button:disabled \{\s*cursor: not-allowed;/);
  assert.match(
    globalStyles,
    /button\[aria-busy='true'\] \{\s*cursor: progress;/,
  );
});

test('reports incomplete board creation and offers managed-original reprocessing', () => {
  assert.match(panelSource, /Pipeline zdjęć:/);
  assert.match(panelSource, /Silnik cięcia plansz:/);
  assert.match(panelSource, /Źródło geometrii 3×3/);
  assert.match(panelSource, /Test ochronny ≥98%/);
  assert.match(panelSource, /geometrySystemicGuard/);
  assert.match(panelSource, /boardCellProcessingJobLabel/);
  assert.match(panelSource, /Wynik jest niekompletny/);
  assert.match(panelSource, /Przetwórz ponownie z oryginałów/);
  assert.match(panelSource, /reprocessImageFolderImport/);
});

test('recovers finalized staging and requires a checksum-bound preflight start', () => {
  assert.match(panelSource, /listReadyBrowserImageSelections/);
  assert.match(panelSource, /previewReadyBrowserImageImport/);
  assert.match(panelSource, /startReadyBrowserImageImport/);
  assert.doesNotMatch(panelSource, /createImageFolderImport|startImport\(/);
  assert.doesNotMatch(actionsSource, /createImageFolderImport/);
  assert.match(panelSource, /Gotowy staging do wznowienia/);
  assert.match(panelSource, /readyBoardImportLifecycleLabel/);
  assert.match(
    panelSource,
    /staging \{ready\.uploadId\.slice\(0, 8\)\} · \{lifecycleLabel\}/,
  );
  assert.match(
    panelSource,
    /Rozpocznij import \$\{geometryEngineVariant === SELECTIVE_BOARD_VARIANT/,
  );
  assert.match(panelSource, /startBrowserPageGeometryPreflight/);
  assert.match(panelSource, /Standardowe v0\.10/);
  assert.match(panelSource, /Obszar plansz — testowe/);
  assert.match(panelSource, /pageRegistrationVariant/);
  assert.match(panelSource, /retryBrowserPageGeometryPreflight/);
  assert.match(panelSource, /geometryPreflightJob\?\.status === 'failed'/);
  assert.match(panelSource, /Ponów preflight/);
  assert.match(panelSource, /preflightResult\.data\.geometryPreflightRequired/);
  assert.match(panelSource, /result\.data\.geometryPreflightRequired/);
  assert.match(panelSource, /preflight\.symbolModelReady/);
  assert.match(panelSource, /preflight\.unclassifiedColdStartAllowed/);
  assert.match(panelSource, /preflight\.symbolModelBlockerCode/);
  assert.match(panelSource, /Model symboli/);
  assert.match(panelSource, /Ulepszaniu modelu symboli/);
  assert.match(panelSource, /aktywuj model tej gry/);
  assert.match(panelSource, /Rozpocznij pierwszy import bez modelu/);
  assert.match(panelSource, /Każda pozycja oznacza jedno zdjęcie/);
  assert.match(panelSource, /Importuj rozpoznane strony/);
  assert.doesNotMatch(panelSource, /<BoardCellProcessingModePicker/);
  assert.match(panelSource, /jobMatchesBoardCellProcessingMode/);
  assert.match(panelSource, /v1\.1 — korekta niepewnych plansz/);
  assert.match(
    panelSource,
    /Ręczna korekta zdjęć geometrii — zostaw na\s+koniec/,
  );
  assert.match(panelSource, /zarejestrowane zdjęcia/);
  assert.doesNotMatch(panelSource, /Import jest zablokowany/);
  assert.match(panelSource, /utworzony — oczekuje na worker/);
  assert.match(panelSource, /Usuń nieużywany staging/);
  assert.match(panelSource, /Import plansz z folderu/);
});

test('refreshes an open report when symbol-model readiness changes', () => {
  const refreshFlow = panelSource.slice(
    panelSource.indexOf('async function refreshStatus'),
    panelSource.indexOf('async function reprocessImport'),
  );

  assert.match(refreshFlow, /previewReadyBrowserImageImport/);
  assert.match(refreshFlow, /refreshedReport/);
  assert.match(refreshFlow, /symbolModelNextStep/);
  assert.match(
    refreshFlow,
    /Status importu i raport modelu zostały odświeżone/,
  );
});

test('shows the real geometry phase and distinguishes provisional from final counts', () => {
  assert.match(panelSource, /pendingGeometryCorrectionState/);
  assert.match(panelSource, /visibleGeometryCorrectionCount/);
  assert.match(panelSource, /jobProgressLabel\(geometryPreflightJob\)/);
  assert.match(
    panelSource,
    /pageGeometryPreflightOutcomeLabel\(\s*geometryPreflightJob,\s*visibleGeometryCorrectionCount/,
  );
  assert.match(
    panelSource,
    /onPendingSourceCountChange=\{\s*handlePendingGeometryCorrectionCountChange\s*\}/,
  );
  assert.match(panelSource, /koniec \(\{visibleGeometryCorrectionCount\}\)/);
});

test('starts page geometry only after the explicit operator action', () => {
  const uploadFlow = panelSource.slice(
    panelSource.indexOf('async function chooseFolder'),
    panelSource.indexOf('async function prepareReadyImport'),
  );
  const reportFlow = panelSource.slice(
    panelSource.indexOf('async function prepareReadyImport'),
    panelSource.indexOf('async function startReadyImport'),
  );
  const explicitFlow = panelSource.slice(
    panelSource.indexOf('async function startGeometryPreflight'),
    panelSource.indexOf('async function retryGeometryPreflight'),
  );

  assert.doesNotMatch(uploadFlow, /startBrowserPageGeometryPreflight/);
  assert.doesNotMatch(reportFlow, /startBrowserPageGeometryPreflight/);
  assert.match(explicitFlow, /startBrowserPageGeometryPreflight/);
  assert.match(panelSource, /Kliknij „Przygotuj geometrię stron”/);
  assert.match(panelSource, /historia zakończonych importów pozostaje w/);
});

test('reopens the completed engine variant and replays a report without dispatch', () => {
  assert.match(panelSource, /v1\.0 — niepełne boki/);
  const stagingActions = panelSource.slice(
    panelSource.indexOf('{readySelections.length > 0 ?'),
    panelSource.indexOf('{active && preflight !== null ?'),
  );
  assert.match(
    stagingActions,
    /readyBoardImportGeometryVariant\(\s*geometryPreflightJobs,\s*ready/,
  );
  assert.match(
    stagingActions,
    /prepareReadyImport\(\s*ready\.uploadId,\s*SELECTIVE_BOARD_VARIANT/,
  );
  assert.match(
    stagingActions,
    /disabled=\{busy \|\| selectiveCapability\?\.enabled !== true\}/,
  );
  assert.match(stagingActions, /Przetwórz w v1\.1/);
  assert.doesNotMatch(stagingActions, /Przetwórz w v1\.0/);
  assert.match(
    panelSource,
    /readyUploadId === uploadId\s*&&\s*geometryEngineVariant === requestedVariant/,
  );
  assert.match(panelSource, /geometryEngineVariants/);
  assert.match(panelSource, /geometryEngineVariantEnabled/);
  assert.match(panelSource, /geometryPreflightArtifactBlockerMessage/);
  assert.match(panelSource, /existingImportJob/);
  assert.match(panelSource, /localStorage/);
  assert.match(panelSource, /Wersja silnika siatki/);
  assert.match(panelSource, /Wariant dopasowania geometrii zdjęcia/);
  assert.match(panelSource, /Wersja modelu symboli/);
  const reportFlow = panelSource.slice(
    panelSource.indexOf('async function prepareReadyImport'),
    panelSource.indexOf('async function startReadyImport'),
  );
  assert.doesNotMatch(reportFlow, /startBrowserPageGeometryPreflight/);
  assert.doesNotMatch(reportFlow, /startReadyBrowserImageImport/);
  const refreshButton = panelSource.slice(
    panelSource.indexOf("geometryPreflightJob?.status === 'failed'"),
    panelSource.indexOf('Odśwież preflight geometrii'),
  );
  assert.match(
    refreshButton,
    /geometryPreflightJob === null\s*\? void startGeometryPreflight\(\)\s*: void refreshStatus\(\)/,
  );
  const refreshJobsFlow = panelSource.slice(
    panelSource.indexOf('const refreshJobs ='),
    panelSource.indexOf(
      'useEffect(() => {',
      panelSource.indexOf('const refreshJobs ='),
    ),
  );
  assert.doesNotMatch(
    refreshJobsFlow,
    /setGeometryEngineVariant\(LATERAL_PARTIAL_VARIANT\)/,
  );
});

test('keeps managed preflight state outside the active browser report', () => {
  const managedFlow = panelSource.slice(
    panelSource.indexOf('async function reprocessManagedV4'),
    panelSource.indexOf('async function inspectSequence'),
  );
  assert.doesNotMatch(managedFlow, /setGeometryPreflightJob\(/);
  assert.match(panelSource, /geometryPreflightMatchesReport/);
  assert.match(panelSource, /activeBrowserGeometryPreflightJob/);
});

test('routes delayed guard results through the latest job ref', () => {
  assert.match(panelSource, /activeGuardJobIdRef/);
  assert.match(panelSource, /persistedGuardContextIdentityStatusFromLatest/);
  assert.doesNotMatch(
    panelSource.slice(
      panelSource.indexOf('const handlePersistedGuardContextLoaded'),
      panelSource.indexOf('const readyImportStartAllowed'),
    ),
    /failedGeometryGuardJob\?\.id/,
  );
});

test('requires explicit board resolutions and pins the sealed manifest to schema v7 start', () => {
  assert.match(panelSource, /IMAGE_GEOMETRY_SYSTEMIC_REGRESSION/);
  assert.match(panelSource, /Rozlicz problematyczne plansze/);
  assert.match(panelSource, /geometryGuardResolutionManifest\?\.id/);
  assert.match(actionsSource, /geometryGuardResolutionManifestChecksumSha256/);
  assert.match(guardResolutionSource, /Odtwórz diagnostykę plansz/);
  assert.match(guardResolutionSource, /Popraw pełną siatkę/);
  assert.match(guardResolutionSource, /Częściowa/);
  assert.match(guardResolutionSource, /Odrzuć/);
  assert.doesNotMatch(guardResolutionSource, /Generuj podgląd A\/B/);
  assert.doesNotMatch(guardResolutionSource, /Plansze na zdjęciu/);
  assert.doesNotMatch(
    guardResolutionSource,
    /previewImageGeometryGuardDecision/,
  );
  assert.match(guardResolutionSource, /geometryGuardDecisionPanel/);
  assert.match(guardResolutionSource, /Zapisz decyzję \(\$\{dirtyCount\}\)/);
  assert.ok(
    guardResolutionSource.indexOf('Zapisz decyzję (${dirtyCount})') <
      guardResolutionSource.indexOf('Następne zdjęcie'),
  );
  const nextPhotoLabel = guardResolutionSource.indexOf('Następne zdjęcie');
  const nextPhotoButton = guardResolutionSource.slice(
    guardResolutionSource.lastIndexOf('<button', nextPhotoLabel),
    nextPhotoLabel,
  );
  assert.match(nextPhotoButton, /setSourceChecksum/);
  assert.doesNotMatch(nextPhotoButton, /saveDecision/);
  assert.match(guardResolutionSource, /zoomPercent/);
  assert.doesNotMatch(
    guardResolutionSource,
    /board\.requiresDecision\s*&&\s*chooseBoard/,
  );
  assert.match(guardResolutionSource, /cropped_or_unreadable/);
  assert.match(guardResolutionSource, /Zamknij manifest decyzji/);
  assert.match(guardResolutionSource, /nie został uruchomiony automatycznie/);
  assert.match(guardResolutionSource, /currentResolutionManifest \?\? null/);
  assert.match(guardResolutionSource, /pageGeometryPreflightJob \?\? null/);
  assert.match(panelSource, /handlePersistedGuardContextLoaded/);
  assert.match(panelSource, /keepsPersistedGuardContext/);
  assert.match(panelSource, /canStartReadyImport/);
});

test('defers geometry guard effect initialization and cancels stale callbacks', () => {
  assert.ok(
    (guardResolutionSource.match(/window\.setTimeout/g) ?? []).length >= 2,
  );
  assert.ok(
    (guardResolutionSource.match(/window\.clearTimeout/g) ?? []).length >= 2,
  );
});

test('offers v1.0 and opt-in v1.1 while preserving historical labels', () => {
  assert.match(panelSource, /v1\.0 — niepełne boki/);
  assert.match(panelSource, /v1\.1 — korekta niepewnych plansz/);
  assert.doesNotMatch(panelSource, /<BoardCellProcessingModePicker/);
  assert.doesNotMatch(panelSource, /changeEnginePolicy/);
  assert.doesNotMatch(panelSource, /v20 — geometria i cropy v19/);
  assert.doesNotMatch(panelSource, /v0\.10 v2 — stabilny silnik strukturalny/);
  assert.doesNotMatch(panelSource, /verifiedV19Confirmed/);
  assert.doesNotMatch(panelSource, /boardCellProcessingStartAllowed/);
  assert.match(
    panelSource,
    /className="secondaryButton"\s*disabled=\{busy \|\| enginePolicy === null\}[\s\S]*?'Wybierz folder'/,
  );
  assert.match(panelSource, /Gotowy staging do wznowienia/);
});

test('provides styled actions and accessible import help', () => {
  assert.match(panelSource, /className="importActionToolbar"/);
  assert.match(panelSource, /className="secondaryButton"/);
  assert.match(panelSource, /aria-label="Pomoc dotycząca akcji importu"/);
  assert.match(panelSource, /role="tooltip"/);
  assert.match(panelSource, /Co robią te akcje\?/);
  assert.match(globalStyles, /\.importActionButtons \{/);
  assert.doesNotMatch(globalStyles, /\.boardCellProcessingModePicker \{/);
  assert.match(globalStyles, /\.importActionHelp:focus-within/);
});

test('orders import actions by workflow priority', () => {
  const toolbarStart = panelSource.indexOf('className="importActionButtons"');
  const toolbarEnd = panelSource.indexOf('className="importActionHelp"');
  const toolbarSource = panelSource.slice(toolbarStart, toolbarEnd);

  assert.ok(toolbarStart >= 0);
  assert.ok(toolbarEnd > toolbarStart);
  assert.ok(
    toolbarSource.indexOf('Rozpocznij import') <
      toolbarSource.indexOf('Wybierz folder'),
  );
  assert.ok(
    toolbarSource.indexOf('Wybierz folder') <
      toolbarSource.indexOf('Odśwież status'),
  );
});

test('contains completeness and source controls inside responsive components', () => {
  assert.match(panelSource, /className="importCompletenessCard"/);
  assert.match(panelSource, /className="importMetrics"/);
  assert.match(panelSource, /className="importMissingSequenceChips"/);
  assert.match(panelSource, /className="importSourceControls"/);
  assert.match(panelSource, /className="importCompactList"/);
  assert.match(globalStyles, /\.importMissingSequenceChips \{/);
  assert.match(globalStyles, /\.importSourceControls \{/);
  assert.match(
    globalStyles,
    /\.importMetrics,\s*\.importSourceControls \{\s*grid-template-columns: 1fr;/,
  );
});

test('isolates folder selection state when the active game changes', () => {
  assert.match(
    workspaceSource,
    /<ImageFolderImportPanel[\s\S]*gameId=\{activeGame\.id\}[\s\S]*key=\{activeGame\.id\}/,
  );
});

test('uses the browser-native directory input without a blocking OS helper', () => {
  assert.match(panelSource, /node\.webkitdirectory = true/);
  assert.match(panelSource, /node\.setAttribute\('webkitdirectory', ''\)/);
  assert.match(panelSource, /type="file"/);
  assert.match(panelSource, /uploadImageFolder/);
  assert.match(panelSource, /Przesyłanie/);
  assert.match(actionsSource, /yieldForUploadProgressPaint/);
  assert.match(actionsSource, /uploaded\.data\.uploadedFileCount/);
  assert.doesNotMatch(panelSource, /Otwieranie…/);
  assert.doesNotMatch(panelSource, /selectImageFolder/);
});
