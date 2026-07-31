import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(
  new URL('../src/features/cleanup/cleanup-control.tsx', import.meta.url),
  'utf8',
);

test('cleanup UI requires preview, exact target and explicit acknowledgement', () => {
  assert.match(source, /loadCleanupPreview/);
  assert.match(source, /typedTarget === preview\.confirmationTarget/);
  assert.match(source, /acknowledged/);
  assert.match(source, /preview\.blockers\.length === 0/);
  assert.match(source, /submitting\.current/);
  assert.match(source, /Nieodwracalna operacja/);
});

test('cleanup UI exposes dependency counts, artifacts and shared retention', () => {
  assert.match(source, /preview\.counts/);
  assert.match(source, /preview\.artifactPaths/);
  assert.match(source, /preview\.retainedSharedArtifactCount/);
  assert.match(source, /Operacja jest obecnie zablokowana/);
});
