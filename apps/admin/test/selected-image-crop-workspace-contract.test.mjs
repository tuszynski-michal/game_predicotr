import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspace = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const viewer = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-viewer.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('bad boundary evidence remains in the uncertainty filter without a preview badge', () => {
  assert.match(
    workspace,
    /selectedImageCropReviewReason\(entry\.result\?\.autoCropProposal\)/u,
  );
  assert.match(workspace, /Niepotwierdzone granice — wymagana korekta/u);
  assert.doesNotMatch(workspace, /selectedImageCropTileBadge/u);
});
const parentWorkspace = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('crop workspace is local and mounted below semi automatic selection', () => {
  assert.match(parentWorkspace, /<SelectedImageCropWorkspace \/>/u);
  assert.match(workspace, /Przytnij wybrane zdjęcia/u);
  assert.doesNotMatch(workspace, /AdminApiClient|fetch\(|jobId|apiBaseUrl/u);
});

test('crop preparation exposes bounded parallel throughput telemetry', () => {
  assert.match(workspace, /performance\.concurrency/u);
  assert.match(workspace, /averageCommittedMs/u);
  assert.match(workspace, /lastAnalysisMs/u);
  assert.match(workspace, /lastWriteMs/u);
  assert.match(workspace, /worker\.decodeMs/u);
  assert.match(workspace, /worker\.renderMs/u);
  assert.match(workspace, /równolegle/u);
  assert.match(workspace, /tempo/u);
});

test('crop review provides an atlas grid and opens only selected corrections in the viewer', () => {
  assert.match(workspace, /<ManualImageViewer/u);
  assert.match(workspace, /preparedCount/u);
  assert.match(workspace, /event\.key === 'ArrowLeft'/u);
  assert.match(workspace, /event\.key === 'ArrowRight'/u);
  assert.match(workspace, /toLocaleLowerCase\('pl-PL'\) === 'f'/u);
  assert.match(workspace, /saveCurrentCorrection/u);
  assert.match(workspace, /Resetuj cięcie/u);
  assert.match(workspace, /proposeSelectedImageCrop/u);
  assert.match(workspace, /Automatyczna propozycja/u);
  assert.match(workspace, /proposal\?\.crop/u);
  assert.match(workspace, /prepareAllSelectedImageCrops/u);
  assert.match(workspace, /Przygotowywanie/u);
  assert.match(workspace, /Popraw zaznaczone/u);
  assert.match(workspace, /Miniaturki przyciętych zdjęć/u);
  assert.match(workspace, /setSelectedImageCropCorrection/u);
  assert.match(workspace, /Ponów błędne/u);
  assert.match(workspace, /Zatwierdź i zakończ przegląd/u);
  assert.match(workspace, /Przelicz nieprzejrzane nowym detektorem/u);
  assert.match(workspace, /canAdoptActiveSelectedImageCropPolicy/u);
  assert.match(workspace, /Przelicz automatyczne do poprawy/u);
  assert.match(workspace, /recalculateAutomaticCorrectionSelectedImageCrops/u);
  assert.match(workspace, /Niepewne/u);
  assert.match(workspace, /Zaznacz wszystkie/u);
  assert.match(workspace, /Odznacz wszystkie/u);
  assert.match(workspace, /replaceSelectedImageCropCorrectionSelection/u);
});

test('each thumbnail can accept or select one automatic crop suggestion', () => {
  assert.match(workspace, /Kliknij pojedynczą miniaturkę/u);
  assert.match(workspace, /automaticSuggestionFileNames/u);
  assert.match(workspace, /zaznacz do poprawy/u);
  assert.match(workspace, /usuń z poprawki/u);
});

test('shared viewer overlay is optional and preserves existing image rendering', () => {
  assert.match(viewer, /readonly imageOverlay\?: ReactNode/u);
  assert.match(viewer, /\{imageOverlay\}/u);
  assert.match(viewer, /state\.visibleImageUrl/u);
  assert.match(viewer, /manualPreviewWindow/u);
});

test('viewport state persists without storing image blobs', () => {
  assert.match(workspace, /scrollLeft: saved\.scrollLeft/u);
  assert.match(workspace, /scrollTop: saved\.scrollTop/u);
  assert.match(workspace, /zoom: saved\.zoom/u);
  assert.doesNotMatch(workspace, /indexedDB[\s\S]*Blob/u);
});

test('reload and preview access require explicit operator actions', () => {
  assert.match(workspace, /Wznów zapisany katalog/u);
  assert.match(workspace, /Wczytaj miniaturki/u);
  assert.match(workspace, /Wyjdź i wybierz inny katalog/u);
  assert.match(workspace, /preparationAbortRef\.current\?\.abort\(\)/u);
  assert.doesNotMatch(workspace, /function restorePrepared/u);
  assert.doesNotMatch(
    workspace,
    /void rebuildAtlases\(result\);[\s\S]*const missing/u,
  );
});

test('a competing crop tab gets a stable actionable message', () => {
  assert.match(workspace, /SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING/u);
  assert.match(workspace, /Pozostaw jedno aktywne okno i odśwież pozostałe/u);
});

test('operator can crop only the active gap fills from the repair manifest', () => {
  assert.match(workspace, /Tylko uzupełnione luki z manifestu/u);
  assert.match(workspace, /sourceSelection/u);
  assert.match(workspace, /changeSourceSelection/u);
  assert.match(
    workspace,
    /listSelectedImageCropSourceDirectories\(\s*parentDirectory,\s*nextSelection/u,
  );
  assert.match(workspace, /parentDirectory !== null \? \(\s*<label>/u);
  assert.match(workspace, /SELECTED_IMAGE_CROP_FILLED_GAPS_EMPTY/u);
});
