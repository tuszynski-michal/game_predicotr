import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/model-quality/model-quality-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const gridSource = await readFile(
  new URL(
    '../src/features/model-quality/grid-quality-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('shows active model, deltas, all symbol coverage and advisory thresholds', () => {
  assert.match(source, /Aktywny model/);
  assert.match(source, /newVerifiedLayoutCount/);
  assert.match(source, /symbolCoverage\.map/);
  assert.match(source, /Progi 100 i 1000 są wskazówką/);
  assert.match(source, /protectedItemCount/);
  assert.match(source, /Ostatnia bramka kandydata/);
  assert.match(source, /rejectionReasons/);
  assert.match(source, /gateReportRelativePath/);
  assert.match(source, /Rejestr i aktywacja modelu/);
  assert.match(source, /Aktywuj ostatniego kandydata/);
  assert.match(source, /Przywróć poprzedni model/);
  assert.match(source, /candidateManifestChecksumSha256/);
});

test('keeps grid calibration separate, gated and future-batch only', () => {
  assert.match(source, /GridQualityPanel/);
  assert.match(source, /Rozpoznawanie symboli/);
  assert.match(source, /Cięcie siatki/);
  assert.match(source, /preview\.cellSampleCount/);
  assert.match(gridSource, /Kalibracja siatki/);
  assert.match(gridSource, /Ulepsz cięcie siatki/);
  assert.match(gridSource, /Aktywuj kandydata/);
  assert.match(gridSource, /tylko nowych partii/);
  assert.match(gridSource, /meanNormalizedCornerError/);
  assert.match(gridSource, /p95NormalizedCornerError/);
  assert.match(gridSource, /recalculableBoardCount/);
  assert.match(gridSource, /currentV19BoardCount/);
  assert.match(gridSource, /geometryVersion/);
  assert.match(gridSource, /cropperVersion/);
  assert.ok(
    source.indexOf('Ulepsz rozpoznawanie') < source.indexOf('Cięcie siatki'),
    'symbol actions must stay inside the symbol workflow before the grid workflow',
  );
  assert.match(source, /aria-labelledby="symbol-quality-workflow-title"/);
  assert.match(source, /aria-labelledby="grid-quality-workflow-title"/);
});

test('requires an explicit checksum-bound confirmation and recovers after errors', () => {
  assert.match(source, /Potwierdź niezmienny manifest/);
  assert.match(source, /expectedManifestChecksumSha256|manifestChecksumSha256/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /Spróbuj ponownie/);
  assert.match(source, /controller\.abort\(\)/);
  assert.match(source, /Ulepsz rozpoznawanie/);
});
