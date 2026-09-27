import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  symbolWriteSession,
  canMutateSymbolRow,
} from '../src/lib/symbol-workflow.ts';
import { allowedRoute, allowedQuery } from '../src/lib/boundary.ts';

test('no autosave, lost response keeps exact request, retry cannot change decision', async () => {
  const calls = [];
  let fail = true;
  const session = symbolWriteSession(async (request) => {
    calls.push(request);
    if (fail) throw Error('lost');
  });
  assert.equal(calls.length, 0);
  assert.equal(session.navigationAllowed, true);
  const body = { request_id: 'stable', op: 'label_decide' };
  await assert.rejects(session.submit(body), /lost/);
  assert.equal(session.pending, body);
  assert.equal(session.navigationAllowed, false);
  await assert.rejects(session.submit({ ...body }), /RETRY_REQUIRED/);
  fail = false;
  await session.submit(body);
  assert.equal(calls.length, 2);
  assert.equal(calls[0], calls[1]);
  assert.equal(session.navigationAllowed, true);
});

test('pending write blocks navigation, reload and a second request', async () => {
  let finish;
  const session = symbolWriteSession(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const running = session.submit({ id: 1 });
  assert.equal(session.navigationAllowed, false);
  assert.throws(() => session.reload(), /PENDING/);
  await assert.rejects(session.submit({ id: 2 }), /PENDING/);
  finish();
  await running;
  assert.equal(session.pending, null);
});

test('DB rows are readonly and proxy routes remain closed', () => {
  assert.equal(canMutateSymbolRow('db_approved'), false);
  assert.equal(canMutateSymbolRow('lab_human_approved'), true);
  assert.equal(allowedRoute('POST', ['symbol-crops']), true);
  assert.equal(
    allowedRoute('POST', ['symbol-dictionaries', 'local-a', '1']),
    false,
  );
  assert.equal(
    allowedRoute('GET', ['symbol-dictionaries', 'local-a', '1']),
    true,
  );
  assert.equal(
    allowedRoute('GET', ['symbol-dictionaries', 'local-a', 'deadbeef']),
    false,
  );
  assert.equal(
    allowedQuery(['symbols'], new URLSearchParams('read_token=abc&offset=50')),
    true,
  );
  assert.equal(
    allowedQuery(['symbol-crops'], new URLSearchParams('path=x'), 'POST'),
    false,
  );
});
