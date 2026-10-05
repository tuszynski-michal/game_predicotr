import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  batchDecision,
  confirmedBatchPage,
} from '../src/lib/symbol-batch-workflow.ts';
import { symbolWriteSession } from '../src/lib/symbol-workflow.ts';

const page = {
  kind: 'batch_queue',
  reference_id: 'reference',
  revision: 0,
  dictionary: {
    entries: [
      { id: 'a', display_name: 'A' },
      { id: 'b', display_name: 'B' },
    ],
  },
  items: [1, 2].map((id) => ({
    case_id: String(id),
    png_base64: 'exact-PNG-' + id,
    symbol_id: null,
  })),
};

test('choice uses only the selected displayed crop; no grid edit or implicit prediction approval', () => {
  assert.equal(
    batchDecision(page, '1', new Set(), 'approve', 'a', 'request'),
    null,
  );
  assert.equal(
    batchDecision(
      page,
      'missing',
      new Set(['missing']),
      'approve',
      'a',
      'request',
    ),
    null,
  );
  assert.equal(
    batchDecision(page, '1', new Set(['1']), 'approve', 'unknown', 'request'),
    null,
  );
  assert.equal(
    batchDecision(page, '1', new Set(['1']), 'grid_issue', 'a', 'request'),
    null,
  );
  const request = batchDecision(
    page,
    '2',
    new Set(['1', '2']),
    'approve',
    'b',
    'request',
  );
  assert.equal(request.case_id, '2');
  assert.equal(request.symbol_id, 'b');
  assert.equal(request.reference_id, page.reference_id);
  assert.equal(request.expected_revision, 0);
  assert.equal(Object.hasOwn(request, 'geometry'), false);
});

test('lost response retries identical request and changes only receipt-confirmed crop', async () => {
  const request = batchDecision(
    page,
    '1',
    new Set(['1']),
    'approve',
    'a',
    'request',
  );
  const result = {
    revision: 1,
    request_id: 'request',
    result_id: 'decision',
    decision_ids: ['decision'],
    trainable: false,
  };
  const calls = [];
  const session = symbolWriteSession(async (body) => {
    calls.push(body);
    if (calls.length === 1) throw new Error('lost response');
    return result;
  });
  await assert.rejects(session.submit(request));
  assert.equal(session.pending, request);
  assert.equal(session.navigationAllowed, false);
  await assert.rejects(
    session.submit({ ...request, symbol_id: 'b' }),
    /RETRY_REQUIRED/,
  );
  const receipt = await session.submit(session.pending);
  assert.equal(calls[0], calls[1]);
  const confirmed = confirmedBatchPage(page, request, receipt);
  assert.equal(confirmed.items[0].symbol_id, 'a');
  assert.equal(confirmed.items[0].png_base64, page.items[0].png_base64);
  assert.equal(confirmed.items[1], page.items[1]);
  assert.equal(confirmed.revision, 1);
  assert.equal(session.navigationAllowed, true);
  for (const bad of [
    { ...result, revision: 9 },
    { ...result, request_id: 'other' },
    { ...result, decision_ids: [] },
  ]) {
    assert.equal(confirmedBatchPage(page, request, bad), null);
  }
  const next = batchDecision(
    confirmed,
    '1',
    new Set(['1']),
    'approve',
    'b',
    'correction',
  );
  assert.equal(next.expected_revision, 1);
});
