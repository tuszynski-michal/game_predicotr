import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const catalogSource = await readFile(
  new URL('../src/features/symbols/symbol-catalog.tsx', import.meta.url),
  'utf8',
);
const previewSource = await readFile(
  new URL(
    '../src/features/symbols/symbol-image-preview-modal.tsx',
    import.meta.url,
  ),
  'utf8',
);
const styles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('offers a preview only for a persisted symbol reference image', () => {
  assert.match(catalogSource, /editor\.symbol\.imagePath !== null/);
  assert.match(catalogSource, />\s*Podgląd\s*</);
  assert.match(catalogSource, /api\.symbolImageAssetUrl/);
  assert.match(catalogSource, /<SymbolImagePreviewModal/);
  assert.match(catalogSource, /Podgląd pokazuje ostatnio zapisaną grafikę/);
});

test('renders an accessible read-only preview with loading and error states', () => {
  assert.match(previewSource, /data-testid="symbol-image-preview"/);
  assert.match(previewSource, /aria-modal="true"/);
  assert.match(previewSource, /Grafika referencyjna symbolu/);
  assert.match(previewSource, /Wczytywanie grafiki/);
  assert.match(previewSource, /Nie udało się wczytać grafiki/);
  assert.match(previewSource, /event\.key === 'Escape'/);
  assert.match(previewSource, /Spróbuj ponownie/);
  assert.doesNotMatch(previewSource, /selectSymbolImageCandidate/);
});

test('keeps the reference image contained and the persisted path readable', () => {
  assert.match(
    styles,
    /\.symbolImagePreviewFrame img \{[\s\S]*object-fit: contain/,
  );
  assert.match(
    styles,
    /\.symbolImagePreviewMetadata code \{[\s\S]*overflow-wrap: anywhere/,
  );
  assert.match(
    styles,
    /\.imagePathControlRow \{[\s\S]*grid-template-columns: minmax\(0, 1fr\) auto/,
  );
});
