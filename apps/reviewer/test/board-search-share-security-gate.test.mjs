/**
 * Security gate of the online board-search share (TASK-0770, D-471/D-472).
 * The proxy allowlist must match the public routes in the OpenAPI artifact
 * exactly: nothing public is unreachable and nothing unlisted is reachable.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { boardSearchShareRoute } from '../src/security/board-search-share-proxy.ts';

const openapi = JSON.parse(
  await readFile(
    new URL(
      '../../../packages/admin-api-client/openapi/openapi.json',
      import.meta.url,
    ),
    'utf8',
  ),
);
const uuid = '11111111-1111-4111-8111-111111111111';

function concrete(path) {
  return path
    .replaceAll('{session_id}', uuid)
    .replaceAll('{symbol_id}', uuid)
    .replaceAll('{sequence_number}', '42');
}

const publicOperations = Object.entries(openapi.paths)
  .filter(([path]) => path.startsWith('/api/v1/board-search-shares/'))
  .flatMap(([path, operations]) =>
    Object.keys(operations).map((method) => [method.toUpperCase(), path]),
  );

test('every public share route in OpenAPI is allowlisted by the proxy', () => {
  assert.equal(publicOperations.length, 8);
  for (const [method, path] of publicOperations) {
    assert.notEqual(
      boardSearchShareRoute(method, concrete(path)),
      null,
      `${method} ${path} must be reachable`,
    );
  }
});

test('the proxy allows no share route that OpenAPI does not publish', () => {
  const published = new Set(
    publicOperations.map(([method, path]) => `${method} ${concrete(path)}`),
  );
  const candidates = [];
  for (const [path, operations] of Object.entries(openapi.paths)) {
    for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']) {
      candidates.push([method, concrete(path)]);
    }
    void operations;
  }
  for (const [method, path] of candidates) {
    if (boardSearchShareRoute(method, path) !== null) {
      assert.ok(
        published.has(`${method} ${path}`),
        `${method} ${path} is not public`,
      );
    }
  }
});

test('no Admin share route (sessions, query log, replay) is reachable', () => {
  const adminShareRoutes = Object.entries(openapi.paths).filter(([path]) =>
    path.startsWith('/api/v1/admin/board-search-shares/'),
  );
  assert.ok(adminShareRoutes.length >= 4);
  for (const [path, operations] of adminShareRoutes) {
    for (const method of Object.keys(operations)) {
      assert.equal(
        boardSearchShareRoute(
          method.toUpperCase(),
          path.replaceAll('{session_id}', uuid).replaceAll('{event_id}', uuid),
        ),
        null,
        `${method} ${path}`,
      );
    }
  }
});

test('public share responses carry no query log, identities or paths', () => {
  const schemas = openapi.components.schemas;
  const publicSchemas = [
    'BoardSearchSharePublicContextResponse',
    'BoardSearchSharePublicSymbolResponse',
    'BoardSearchSharePublicSearchResponse',
    'BoardSearchSharePublicSearchResultResponse',
  ];
  for (const name of publicSchemas) {
    const properties = Object.keys(schemas[name].properties).map((key) =>
      key.toLowerCase(),
    );
    for (const forbidden of [
      'reviewitemid',
      'recognizedboardid',
      'importjobid',
      'imagepath',
      'gameid',
      'outcomecode',
      'request',
    ]) {
      assert.ok(!properties.includes(forbidden), `${name}.${forbidden}`);
    }
  }
});
