import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panelSource = await readFile(
  new URL(
    '../src/features/symbols/symbol-bootstrap-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);
const globalStyles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('keeps the symbol bootstrap entry compact and uses the accepted label', () => {
  assert.doesNotMatch(panelSource, /Automatyczny katalog/);
  assert.doesNotMatch(panelSource, /Utwórz symbole z zaimportowanych cropów/);
  assert.doesNotMatch(panelSource, /Analiza zachowuje rzeczywisty obraz/);
  assert.match(panelSource, /<span>Liczba symboli<\/span>/);
});

test('uses a scoped styled number control instead of an unstyled input', () => {
  assert.match(panelSource, /className="symbolBootstrapControls"/);
  assert.match(panelSource, /className="symbolBootstrapCountField"/);
  assert.match(globalStyles, /\.symbolBootstrapCountField input \{/);
  assert.match(
    globalStyles,
    /\.symbolBootstrapCountField input:focus-visible \{/,
  );
});
