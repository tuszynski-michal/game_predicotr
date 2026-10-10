import test from 'node:test';
import assert from 'node:assert/strict';
import {
  interpolateCorners,
  activeIntervals,
} from '../src/lib/annotation-geometry.ts';
import { allowedRoute } from '../src/lib/boundary.ts';
test('corner interpolation remains a proposal for both topologies', () => {
  const corners = [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 60 },
    { x: 0, y: 60 },
  ];
  for (const columns of [3, 5]) {
    const nodes = interpolateCorners(corners, columns);
    assert.equal(nodes.length, (columns + 1) * 4);
    assert.ok(nodes.every((p) => p.provenance === 'baseline_proposal'));
  }
});
test('idle intervals over 30 seconds are excluded', () =>
  assert.equal(activeIntervals([1000, 30000, 30001, 2500]), 33500));
test('new routes remain explicitly allowlisted', () => {
  for (const route of ['annotations', 'families', 'splits', 'backups'])
    assert.ok(allowedRoute('POST', [route]));
  assert.equal(allowedRoute('POST', ['restore']), false);
  assert.equal(allowedRoute('POST', ['annotations', 'arbitrary']), false);
});
