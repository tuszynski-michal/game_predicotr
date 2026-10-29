import test from 'node:test';
import assert from 'node:assert/strict';
import { SelectionIntents } from '../src/renderer/selection-intents.ts';
import { ShutdownHandshake } from '../src/native/desktop-lifecycle.ts';

const initial = () => ({
  projectId: 'project',
  revision: 1,
  source: { id: 'source', images: ['a', 'b', 'c', 'd'].map((id) => ({ id })) },
  currentImageId: 'a',
  nextRangeStart: 1,
  direction: 'ascending',
  sequenceUpperBound: 500000,
  acceptedImageIds: [],
  acceptedCount: 0,
  decisionCount: 0,
  selectionComplete: false,
  issue: null,
  view: {},
});
function delta(workspace) {
  const { source, ...scalars } = workspace;
  return { ...scalars, sourceId: source?.id ?? null };
}
const turn = () => new Promise((resolve) => setImmediate(resolve));
function fixture() {
  let state = initial();
  let clock = 0;
  let counter = 0;
  const frames = [],
    requests = [],
    responses = [];
  const machine = new SelectionIntents({
    frame: (cb) => frames.push(cb),
    operationId: () => `operation-${++counter}`,
    now: () => clock,
    changed: () => {},
    snapshot: async () => ({ ok: true, value: structuredClone(state) }),
    execute: (request) => {
      requests.push(request);
      return new Promise((resolve, reject) =>
        responses.push({ request, resolve, reject }),
      );
    },
  });
  machine.install(state);
  return {
    machine,
    requests,
    responses,
    frames,
    setClock: (n) => {
      clock = n;
    },
    frame() {
      for (const callback of frames.splice(0)) callback();
    },
    state: () => state,
    commit(response = responses.shift()) {
      const { request, resolve } = response;
      state = { ...state, revision: state.revision + 1 };
      if (request.command.kind === 'navigate')
        state.currentImageId = request.command.imageId;
      if (request.command.kind === 'accept') {
        const index = state.source.images.findIndex(
          (image) => image.id === request.command.imageId,
        );
        state.currentImageId = state.source.images[Math.min(index + 1, 3)].id;
        state.nextRangeStart += 9;
        state.acceptedCount++;
        state.acceptedImageIds = [
          ...state.acceptedImageIds,
          request.command.imageId,
        ];
      }
      resolve({ ok: true, value: delta(structuredClone(state)) });
    },
  };
}

test('navigation is optimistic, bounded and combines unsent directions without stale rollback', async () => {
  const f = fixture();
  f.machine.move(1);
  f.frame();
  await turn();
  assert.equal(f.requests.length, 1);
  f.machine.move(2);
  f.machine.move(-1);
  f.machine.move(1);
  f.frame();
  assert.equal(f.machine.displayedImageId, 'd');
  assert.equal(f.machine.pendingNavigation, 'd');
  assert.equal(f.requests.length, 1);
  f.commit();
  await turn();
  assert.equal(f.machine.displayedImageId, 'd');
  assert.equal(f.requests.length, 2);
  f.commit();
  await turn();
  assert.equal(f.machine.workspace.currentImageId, 'd');
  assert.equal(f.machine.phase, 'idle');
});

test('range and undo on the same ready target allow F without another decode', async () => {
  for (const command of [
    { kind: 'range', start: 499987, direction: 'descending' },
    { kind: 'undo' },
  ]) {
    const f = fixture();
    f.machine.decoded('a');
    f.machine.command(command);
    await turn();
    f.responses
      .shift()
      .resolve({
        ok: true,
        value: {
          ...delta(initial()),
          revision: 2,
          nextRangeStart: 499987,
          direction: 'descending',
        },
      });
    await turn();
    assert.equal(f.machine.readyImageId, 'a');
    f.machine.accept();
    await turn();
    assert.equal(f.requests.length, 2);
    assert.equal(f.requests[1].command.kind, 'accept');
    assert.equal(f.requests[1].command.imageId, 'a');
    assert.equal(f.machine.acceptIntent.rangeStart, 499987);
    assert.equal(f.machine.acceptIntent.direction, 'descending');
  }
});

test('non-navigation response with a changed target still waits for that target decode', async () => {
  const f = fixture();
  f.machine.decoded('a');
  f.machine.command({ kind: 'undo' });
  await turn();
  f.responses
    .shift()
    .resolve({
      ok: true,
      value: { ...delta(initial()), revision: 2, currentImageId: 'b' },
    });
  await turn();
  assert.equal(f.machine.readyImageId, null);
  f.machine.accept();
  await turn();
  assert.equal(f.requests.length, 1);
  f.machine.decoded('a');
  await turn();
  assert.equal(f.requests.length, 1);
  f.machine.decoded('b');
  await turn();
  assert.equal(f.requests.length, 2);
  assert.equal(f.requests[1].command.imageId, 'b');
});

test('arrow then F pins new target and waits for both navigation and decode, with one accept', async () => {
  const f = fixture();
  f.machine.decoded('a');
  f.machine.move(1);
  f.frame();
  await turn();
  f.machine.accept();
  const pinned = f.machine.acceptIntent;
  assert.equal(pinned.imageId, 'b');
  assert.equal(pinned.rangeStart, 1);
  f.machine.accept();
  f.machine.move(2);
  f.machine.command({ kind: 'skip' });
  assert.equal(f.machine.acceptIntent, pinned);
  assert.equal(f.machine.displayedImageId, 'b');
  f.commit();
  await turn();
  assert.equal(f.requests.length, 1);
  assert.equal(f.machine.workspace.nextRangeStart, 1);
  f.machine.decoded('b');
  await turn();
  assert.equal(f.requests.length, 2);
  assert.deepEqual(f.requests[1], pinned.request);
  f.machine.cancelAccept();
  assert.equal(f.machine.acceptIntent.dispatched, true);
  f.commit();
  await turn();
  assert.equal(f.machine.displayedImageId, 'c');
  assert.equal(f.machine.workspace.nextRangeStart, 10);
  assert.deepEqual(f.machine.workspace.acceptedImageIds, ['b']);
});

test('F before decode can be explicitly cancelled and never dispatches later', async () => {
  const f = fixture();
  f.machine.accept();
  assert.equal(f.machine.message, 'Oczekuje na zapis');
  f.machine.cancelAccept();
  f.machine.decoded('a');
  await turn();
  assert.equal(f.requests.length, 0);
  assert.equal(f.machine.acceptIntent, null);
});

test('timeout cancels only unsent accept and does not release the native writer', async () => {
  const f = fixture();
  f.machine.move(1);
  f.frame();
  await turn();
  f.machine.accept();
  f.setClock(10000);
  f.machine.expire();
  assert.equal(f.machine.acceptIntent, null);
  assert.match(f.machine.message, /podgląd nie jest gotowy/);
  assert.equal(f.machine.mutating, true);
  f.machine.decoded('b');
  assert.equal(f.requests.length, 1);
  f.commit();
  await turn();
  assert.equal(f.requests.length, 1);
});

test('decode failure cancels target F and a late decode of another image cannot accept', async () => {
  const f = fixture();
  f.machine.move(1);
  f.machine.accept();
  await turn();
  f.machine.decoded('a');
  f.commit();
  await turn();
  assert.equal(f.requests.length, 1);
  f.machine.decoded(null, 'b');
  f.machine.decoded('b');
  await turn();
  assert.equal(f.machine.acceptIntent, null);
  assert.equal(f.requests.length, 1);
  assert.match(f.machine.message, /JPEG/);
});

test('context conflict and old project/source/revision responses fail closed', async () => {
  for (const patch of [
    { source: { id: 'other', images: [] } },
    { projectId: 'other' },
    { revision: 0 },
  ]) {
    const f = fixture();
    f.machine.move(1);
    f.frame();
    await turn();
    f.machine.accept();
    f.responses
      .shift()
      .resolve({ ok: true, value: { ...initial(), ...patch } });
    await turn();
    assert.equal(f.machine.phase, 'error');
    assert.equal(f.requests.length, 1);
    assert.equal(f.machine.acceptIntent, null);
  }
});

test('navigation changing the range rejects pinned F instead of selecting another range', async () => {
  const f = fixture();
  f.machine.move(1);
  f.frame();
  await turn();
  f.machine.accept();
  f.responses.shift().resolve({
    ok: true,
    value: {
      ...delta(initial()),
      revision: 2,
      currentImageId: 'b',
      nextRangeStart: 31,
    },
  });
  await turn();
  f.machine.decoded('b');
  await turn();
  assert.equal(f.requests.length, 1);
  assert.match(f.machine.message, /zakres/);
  assert.equal(f.machine.phase, 'error');
});

test('lost accept response retries identical operationId once and uses receipt result', async () => {
  const f = fixture();
  f.machine.decoded('a');
  f.machine.accept();
  await turn();
  const first = f.responses.shift();
  first.reject(new Error('response lost'));
  await turn();
  assert.equal(f.requests.length, 2);
  assert.deepEqual(f.requests[0], f.requests[1]);
  f.commit();
  await turn();
  assert.equal(f.machine.workspace.acceptedCount, 1);
  assert.equal(f.machine.phase, 'idle');
});

test('snapshot rejection is handled and explicit retry keeps operationId', async () => {
  const f = fixture();
  f.machine.effects.snapshot = async () => {
    throw new Error('snapshot lost');
  };
  f.machine.decoded('a');
  f.machine.accept();
  await turn();
  f.responses.shift().reject(new Error('response lost'));
  await turn();
  assert.equal(f.machine.phase, 'error');
  assert.match(f.machine.message, /snapshot lost/);
  f.machine.move(1);
  f.machine.command({ kind: 'undo' });
  assert.equal(f.requests.length, 1);
  f.machine.retry();
  await turn();
  assert.deepEqual(f.requests[0], f.requests[1]);
  f.commit();
  await turn();
  assert.equal(f.machine.phase, 'idle');
});

test('failed automatic retry leaves mutations blocked without a retry loop', async () => {
  const f = fixture();
  f.machine.decoded('a');
  f.machine.accept();
  await turn();
  f.responses.shift().reject(new Error('lost'));
  await turn();
  f.responses.shift().reject(new Error('lost again'));
  await turn();
  assert.equal(f.requests.length, 2);
  assert.equal(f.machine.phase, 'error');
  f.machine.retry();
  await turn();
  assert.deepEqual(f.requests[0], f.requests[2]);
  f.commit();
  await turn();
});

test('close rejects unsent accept; after cancellation flushes last unsent navigation', async () => {
  const f = fixture();
  f.machine.move(2);
  f.machine.accept();
  await turn();
  await assert.rejects(f.machine.flushForClose(), /Anuluj/);
  assert.equal(f.machine.closing, false);
  f.machine.cancelAccept();
  f.machine.move(1);
  f.frame();
  const close = f.machine.flushForClose();
  f.machine.move(-1);
  f.commit();
  await turn();
  assert.equal(f.requests.length, 2);
  f.commit();
  await close;
  assert.equal(f.machine.workspace.currentImageId, 'd');
  assert.equal(f.machine.closing, true);
});

test('shutdown handshake validates token/project, permits refusal and never forces timeout', async () => {
  const handshake = new ShutdownHandshake();
  let request;
  const pending = handshake.request('p', (value) => {
    request = value;
  });
  assert.throws(
    () => handshake.reply({ ...request, token: 'old', ready: true }, 'p'),
    { code: 'INVALID_SHUTDOWN' },
  );
  assert.throws(() => handshake.reply({ ...request, ready: true }, 'other'), {
    code: 'INVALID_SHUTDOWN',
  });
  handshake.reply({ ...request, ready: true }, 'p');
  await pending;
  const refused = handshake.request(null, (value) => {
    request = value;
  });
  handshake.reply({ ...request, ready: false, message: 'waiting' }, null);
  await assert.rejects(refused, { code: 'SHUTDOWN_PENDING' });
  await assert.rejects(
    handshake.request('p', () => {}, 5),
    { code: 'SHUTDOWN_TIMEOUT' },
  );
  const retried = handshake.request('p', (value) => {
    request = value;
  });
  handshake.reply({ ...request, ready: true }, 'p');
  await retried;
});

test('explicit native failure permits existing recovery and safe close; unknown response does not', async () => {
  const f = fixture();
  f.machine.decoded('a');
  f.machine.accept();
  await turn();
  f.responses
    .shift()
    .resolve({ ok: false, error: { code: 'LOCK_LOST', message: 'lock lost' } });
  await turn();
  assert.equal(f.machine.phase, 'error');
  assert.equal(f.machine.recoverableError, true);
  assert.equal(f.machine.acceptIntent, null);
  await f.machine.flushForClose();
  assert.equal(f.machine.closing, true);

  const unknown = fixture();
  unknown.machine.effects.snapshot = async () => {
    throw new Error('offline');
  };
  unknown.machine.decoded('a');
  unknown.machine.accept();
  await turn();
  unknown.responses.shift().reject(new Error('lost'));
  await turn();
  assert.equal(unknown.machine.recoverableError, false);
  await assert.rejects(unknown.machine.flushForClose(), /Nie potwierdzono/);
});

test('a decision in flight visibly rejects F and does not consume later navigation', async () => {
  const f = fixture();
  f.machine.command({ kind: 'skip' });
  await turn();
  f.machine.move(2);
  f.machine.accept();
  assert.equal(f.machine.displayedImageId, 'a');
  assert.equal(f.machine.acceptIntent, null);
  assert.match(f.machine.message, /Nie zapisano/);
  f.commit();
  await turn();
  assert.equal(f.requests.length, 1);
});

for (const invalid of [
  { sourceId: 'foreign' },
  { projectId: 'foreign' },
  { revision: 0 },
  { currentImageId: 'missing' },
]) {
  test(`invalid delta ${JSON.stringify(invalid)} falls back to snapshot and blocks accept`, async () => {
    const f = fixture();
    let snapshots = 0;
    f.machine.effects.snapshot = async () => {
      snapshots++;
      return { ok: true, value: structuredClone(f.state()) };
    };
    f.machine.move(1);
    f.frame();
    await turn();
    f.responses.shift().resolve({
      ok: true,
      value: { ...delta(initial()), revision: 2, ...invalid },
    });
    await turn();
    assert.equal(snapshots, 1);
    assert.equal(f.machine.workspace.source.id, 'source');
    assert.equal(f.machine.phase, 'error');
    f.machine.accept();
    assert.equal(f.requests.length, 1);
    f.machine.retry();
    await turn();
    f.commit();
    await turn();
    assert.equal(f.machine.phase, 'idle');
    assert.equal(f.machine.workspace.currentImageId, 'b');
  });
}
