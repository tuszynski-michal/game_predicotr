import assert from 'node:assert/strict';
import test from 'node:test';

import {
  rejectDeferredSlot,
  rejectReviewItem,
} from '../src/features/operational-reviews/board-rejection-actions.ts';
import {
  BOARD_REJECTION_REASONS,
  MAX_BOARD_REJECTION_NOTE_LENGTH,
  boardRejectionCommand,
  boardRejectionDraftError,
  boardRejectionNote,
  boardRejectionReasonLabel,
  boardRejectionReasonText,
  slotRejectionCommand,
} from '../src/features/operational-reviews/board-rejection-state.ts';
import {
  isDefiniteRefusal,
  runMutation,
} from '../src/features/operational-reviews/mutation-outcome.ts';

const key = '44444444-4444-4444-8444-444444444444';
const scope = {
  gameId: '22222222-2222-4222-8222-222222222222',
  importJobId: '33333333-3333-4333-8333-333333333333',
};

test('the picker offers the three reasons of the plan in Polish', () => {
  assert.deepEqual(
    BOARD_REJECTION_REASONS.map((entry) => [entry.value, entry.label]),
    [
      ['cropped', 'Plansza przycięta'],
      ['blurred', 'Rozmyta'],
      ['other', 'Inny'],
    ],
  );
  assert.equal(boardRejectionReasonLabel('blurred'), 'Rozmyta');
  assert.equal(boardRejectionReasonLabel(null), 'Nie podano powodu');
});

test('a draft needs a reason, and the reason "Inny" a bounded note', () => {
  assert.match(boardRejectionDraftError(null, ''), /Wybierz powód/);
  assert.equal(boardRejectionDraftError('cropped', ''), '');
  assert.equal(boardRejectionDraftError('blurred', '  stray note '), '');
  assert.match(boardRejectionDraftError('other', '   '), /opisz/);
  assert.equal(boardRejectionDraftError('other', 'Ucięty górny rząd'), '');
  assert.match(
    boardRejectionDraftError(
      'other',
      'x'.repeat(MAX_BOARD_REJECTION_NOTE_LENGTH + 1),
    ),
    /najwyżej/,
  );
});

test('only the reason "Inny" carries a note, and the board text encodes it', () => {
  assert.equal(boardRejectionNote('cropped', 'ignored'), null);
  assert.equal(boardRejectionNote('other', '  Ucięty  '), 'Ucięty');
  assert.equal(boardRejectionReasonText('cropped', 'ignored'), 'cropped');
  assert.equal(boardRejectionReasonText('blurred', ''), 'blurred');
  assert.equal(
    boardRejectionReasonText('other', ' Ucięty górny rząd '),
    'other: Ucięty górny rząd',
  );
});

test('the slot command pins the slot revision and the board command the review revision', () => {
  const request = { idempotencyKey: key, note: 'Ucięty', reason: 'other' };
  assert.deepEqual(slotRejectionCommand(request, 3), {
    expectedGeometryRevision: 3,
    idempotencyKey: key,
    note: 'Ucięty',
    reason: 'other',
  });
  assert.equal(
    slotRejectionCommand({ ...request, reason: 'cropped' }, 0).note,
    null,
  );
  assert.deepEqual(
    boardRejectionCommand(request, {
      geometryRevision: 2,
      resolutionRevision: 5,
    }),
    {
      action: 'rejected',
      cells: [],
      expectedRevision: 5,
      geometryRevision: 2,
      idempotencyKey: key,
      rejectionReason: 'other: Ucięty',
      resolvedBy: 'local-admin',
      sequenceNumber: null,
    },
  );
});

test('only a 4xx response with an API code is a definite refusal', () => {
  const refused = (status, error) => ({ error, response: { status } });
  assert.equal(
    isDefiniteRefusal(refused(409, { code: 'BOARD_REJECT_CANONICAL' })),
    true,
  );
  assert.equal(isDefiniteRefusal(refused(503, { code: 'UNAVAILABLE' })), false);
  assert.equal(isDefiniteRefusal(refused(409, 'text')), false);
  assert.equal(isDefiniteRefusal({ error: new Error('x') }), false);
  assert.equal(isDefiniteRefusal(null), false);
});

test('runMutation classifies done, refused and every unknown outcome', async () => {
  const done = await runMutation(async () => ({ data: { ok: 1 } }), 'x');
  assert.deepEqual(done, { data: { ok: 1 }, kind: 'done' });

  const refused = await runMutation(
    async () => ({
      error: { code: 'BOARD_REJECT_CANONICAL', message: 'Kanoniczna.' },
      response: { status: 409 },
    }),
    'x',
  );
  assert.equal(refused.kind, 'refused');
  assert.equal(refused.code, 'BOARD_REJECT_CANONICAL');
  assert.match(refused.message, /Kanoniczna\. \(BOARD_REJECT_CANONICAL\)/);

  for (const request of [
    async () => {
      throw new TypeError('fetch failed');
    },
    async () => ({ error: new Error('no response') }),
    async () => ({
      error: { code: 'UNAVAILABLE', message: 'm' },
      response: { status: 503 },
    }),
    async () => null,
  ]) {
    const unknown = await runMutation(request, 'x');
    assert.equal(unknown.kind, 'unknown');
    assert.match(unknown.message, /Wynik operacji jest nieznany/);
  }

  const hung = await runMutation(() => new Promise(() => {}), 'x', 20);
  assert.equal(hung.kind, 'unknown');
});

/** A client double that records the calls and answers from a script. */
function harness(script) {
  const calls = [];
  const answer = (name) => async (id, context, command) => {
    calls.push({ command, context, id, name });
    return script(calls.length);
  };
  return {
    calls,
    client: {
      rejectPendingBoardCellGeometry: answer('rejectPendingBoardCellGeometry'),
      resolveOperationalImageReviewItem: answer(
        'resolveOperationalImageReviewItem',
      ),
    },
  };
}

const refusal = (status, error) => ({ error, response: { status } });

test('a deferred slot is rejected through its rejection operation', async () => {
  const { calls, client } = harness(() => ({ data: { created: true } }));
  const outcome = await rejectDeferredSlot(
    client,
    scope,
    {
      expectedGeometryRevision: 4,
      pendingGeometryId: '11111111-1111-4111-8111-111111111111',
    },
    { idempotencyKey: key, note: '', reason: 'cropped' },
  );

  assert.equal(outcome.kind, 'done');
  assert.deepEqual(calls, [
    {
      command: {
        expectedGeometryRevision: 4,
        idempotencyKey: key,
        note: null,
        reason: 'cropped',
      },
      context: scope,
      id: '11111111-1111-4111-8111-111111111111',
      name: 'rejectPendingBoardCellGeometry',
    },
  ]);
});

test('a board is rejected through the resolution operation and the canonical owner is a refusal', async () => {
  const { calls, client } = harness(() =>
    refusal(409, {
      code: 'BOARD_REJECT_CANONICAL',
      message: 'Ta plansza jest kanonicznym właścicielem swojej sekwencji.',
    }),
  );
  const outcome = await rejectReviewItem(
    client,
    scope,
    {
      geometryRevision: 2,
      resolutionRevision: 7,
      reviewItemId: '55555555-5555-4555-8555-555555555555',
    },
    { idempotencyKey: key, note: 'Ucięty', reason: 'other' },
  );

  assert.equal(outcome.kind, 'refused');
  assert.equal(outcome.code, 'BOARD_REJECT_CANONICAL');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, 'resolveOperationalImageReviewItem');
  assert.equal(calls[0].id, '55555555-5555-4555-8555-555555555555');
  assert.deepEqual(calls[0].context, scope);
  assert.equal(calls[0].command.action, 'rejected');
  assert.equal(calls[0].command.rejectionReason, 'other: Ucięty');
  assert.equal(calls[0].command.expectedRevision, 7);
  assert.equal(calls[0].command.geometryRevision, 2);
});

test('a 5xx or a thrown call is an unknown outcome the caller replays with the same request', async () => {
  const { calls, client } = harness((attempt) => {
    if (attempt === 1) throw new TypeError('fetch failed');
    return refusal(503, { code: 'UNAVAILABLE', message: 'm' });
  });
  const slot = {
    expectedGeometryRevision: 0,
    pendingGeometryId: '11111111-1111-4111-8111-111111111111',
  };
  const request = { idempotencyKey: key, note: '', reason: 'blurred' };

  const first = await rejectDeferredSlot(client, scope, slot, request);
  const second = await rejectDeferredSlot(client, scope, slot, request);

  assert.equal(first.kind, 'unknown');
  assert.equal(second.kind, 'unknown');
  assert.deepEqual(calls[1], calls[0]);
});
