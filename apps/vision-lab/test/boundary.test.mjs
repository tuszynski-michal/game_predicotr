import test from 'node:test';
import assert from 'node:assert/strict';
import { boundary, allowedRoute, allowedQuery } from '../src/lib/boundary.ts';
test('Host, Origin and JSON boundary is fail closed', () => {
  const request = (headers, method = 'POST') =>
    new Request('http://127.0.0.1:3102/api/lab/geometry', { method, headers });
  const good = {
    host: '127.0.0.1:3102',
    origin: 'http://127.0.0.1:3102',
    'content-type': 'application/json',
  };
  assert.equal(boundary(request(good)), null);
  assert.equal(boundary(request({ ...good, host: 'evil.test' })).status, 403);
  assert.equal(
    boundary(request({ ...good, origin: 'http://evil.test' })).status,
    403,
  );
  assert.equal(
    boundary(request({ host: good.host, 'content-type': 'application/json' }))
      .status,
    403,
  );
  assert.equal(
    boundary(request({ ...good, 'content-type': 'text/plain' })).status,
    415,
  );
  assert.equal(boundary(request({ host: good.host }, 'GET')), null);
});
test('training routes and pagination remain closed', () => {
  assert.equal(
    allowedQuery(['runs'], new URLSearchParams('offset=1'), 'POST'),
    false,
  );
  const id = 'a'.repeat(32);
  assert.equal(allowedRoute('POST', ['runs']), true);
  assert.equal(allowedRoute('GET', ['runs', id]), true);
  assert.equal(allowedRoute('POST', ['runs', id, 'cancel']), true);
  assert.equal(allowedRoute('POST', ['runs', id, 'retry']), true);
  assert.equal(allowedRoute('POST', ['runs', id, 'execute']), false);
  assert.equal(allowedRoute('GET', ['runs', '../secret']), false);
  assert.equal(
    allowedQuery(['runs'], new URLSearchParams('offset=1&limit=2')),
    true,
  );
  assert.equal(
    allowedQuery(['runs'], new URLSearchParams('game=private')),
    false,
  );
  assert.equal(
    allowedQuery(['runs', id], new URLSearchParams('offset=1')),
    false,
  );
});
test('proxy permits only registered route shapes', () => {
  assert.equal(allowedRoute('GET', ['sources']), true);
  assert.equal(allowedRoute('POST', ['geometry']), true);
  assert.equal(allowedRoute('GET', ['assets', 'a'.repeat(64)]), true);
  for (const parts of [
    ['admin'],
    ['assets', '..'],
    ['assets', 'C:\\secret'],
    ['sources', 'extra'],
  ])
    assert.equal(allowedRoute('GET', parts), false);
  assert.equal(allowedRoute('POST', ['sources']), false);
});
