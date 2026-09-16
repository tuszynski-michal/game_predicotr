import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const styles = readFileSync(
  new URL(
    '../src/features/symbol-reviews/symbol-review-workspace.module.css',
    import.meta.url,
  ),
  'utf8',
);

test('symbol review thumbnails fill their card and draw the border over the image edge', () => {
  assert.match(styles, /\.card\s*\{[\s\S]*?border:\s*0;/);
  assert.match(styles, /\.card\s*\{[\s\S]*?background:\s*transparent;/);
  assert.match(styles, /\.cardToggle::after\s*\{[\s\S]*?inset:\s*0;/);
  assert.match(styles, /\.cardToggle::after\s*\{[\s\S]*?border:\s*1px solid var\(--line\);/);
  assert.match(styles, /\.virtualPreview\s*\{[\s\S]*?background-color:\s*transparent;/);
  assert.doesNotMatch(styles, /\.virtualPreview\s*\{[\s\S]*?background:\s*#050b14;/);
});
