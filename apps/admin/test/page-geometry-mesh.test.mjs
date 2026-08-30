import assert from 'node:assert/strict';
import test from 'node:test';

import {
  appendPageGeometryCorner,
  applyPageGeometryMeshOverrides,
  completePageGeometryCorners,
  createPageGeometryMesh,
  PAGE_MESH_POINT_COUNT,
  pageGeometryQuadsFromMesh,
} from '../src/features/imports/page-geometry-mesh.ts';

test('collects four page corners in explicit LT PT PD LD click order', () => {
  const points = [
    { x: 10, y: 10 },
    { x: 90, y: 10 },
    { x: 90, y: 90 },
    { x: 10, y: 90 },
  ];
  const draft = points.reduce(
    (current, point) => appendPageGeometryCorner(current, point),
    [],
  );

  assert.deepEqual(completePageGeometryCorners(draft), points);
  assert.deepEqual(appendPageGeometryCorner(draft, { x: 50, y: 50 }), points);
});

test('rejects crossed or counter-clockwise corner click order', () => {
  assert.equal(
    completePageGeometryCorners([
      { x: 10, y: 10 },
      { x: 90, y: 90 },
      { x: 90, y: 10 },
      { x: 10, y: 90 },
    ]),
    null,
  );
  assert.equal(
    completePageGeometryCorners([
      { x: 10, y: 10 },
      { x: 10, y: 90 },
      { x: 90, y: 90 },
      { x: 90, y: 10 },
    ]),
    null,
  );
});

const corners = [
  { x: 0, y: 0 },
  { x: 300, y: 0 },
  { x: 300, y: 300 },
  { x: 0, y: 300 },
];

test('creates a 6x6 edge mesh with gutters and nine row-major page quads', () => {
  const mesh = createPageGeometryMesh(corners);
  const quads = pageGeometryQuadsFromMesh(mesh);

  assert.equal(mesh.length, PAGE_MESH_POINT_COUNT);
  assert.equal(quads.length, 9);
  assert.deepEqual(quads[0]?.[0], { x: 0, y: 0 });
  assert.ok(Math.abs(quads[0][1].x - 88) < 0.001);
  assert.ok(Math.abs(quads[0][2].y - 88) < 0.001);
  assert.deepEqual(quads[8]?.[2], { x: 300, y: 300 });
  assert.ok(Math.abs(quads[8][0].x - 212) < 0.001);
  assert.ok(Math.abs(quads[8][0].y - 212) < 0.001);
  assert.ok(quads[0][1].x < quads[1][0].x);
  assert.ok(quads[0][2].y < quads[3][0].y);
});

test('lets one frame corner bend a board without closing neighbouring gutters', () => {
  const base = createPageGeometryMesh(corners);
  const mesh = applyPageGeometryMeshOverrides(
    base,
    new Map([[7, { x: 92, y: 114 }]]),
  );
  const quads = pageGeometryQuadsFromMesh(mesh);

  assert.deepEqual(mesh[0], corners[0]);
  assert.deepEqual(mesh[35], corners[2]);
  assert.deepEqual(quads[0]?.[2], { x: 92, y: 114 });
  assert.notDeepEqual(quads[1]?.[3], { x: 92, y: 114 });
  assert.notDeepEqual(quads[3]?.[1], { x: 92, y: 114 });
});

test('returns no quads for an incomplete control mesh', () => {
  assert.deepEqual(pageGeometryQuadsFromMesh([{ x: 0, y: 0 }]), []);
});
