import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const workspaceSource = readFileSync(
  new URL(
    '../src/features/symbol-reviews/symbol-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('symbol review exposes catalog and unknown filtering', () => {
  assert.match(workspaceSource, />Wszystkie symbole</);
  assert.match(workspaceSource, />Nierozpoznany \(\?\)</);
  assert.match(workspaceSource, /symbolId: filters\.symbolId \?\? 'all'/);
});

test('symbol review uses only the persisted current crop renderer', () => {
  assert.match(workspaceSource, /previewAnchorCellId\.current,\s*'current'/);
  assert.doesNotMatch(workspaceSource, /Eksperymentalny silnik v0\.10/);
  assert.doesNotMatch(workspaceSource, /Podgląd eksperymentalny v0\.10/);
  assert.doesNotMatch(workspaceSource, /setPreviewMode/);
});
