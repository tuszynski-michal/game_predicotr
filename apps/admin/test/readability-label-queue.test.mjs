import assert from 'node:assert/strict';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import {
  createReadabilityLabelQueue,
  drainReadabilityLabelQueue,
  discardReadabilityLabelQueue,
  loadReadabilityLabelQueue,
  readabilityQueueProgress,
} from '../src/features/readability/readability-label-queue.ts';

function storage() {
  const saved = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => saved.get(key) ?? null,
      setItem: (key, value) => saved.set(key, value),
      removeItem: (key) => saved.delete(key),
    },
  };
  return saved;
}
const payload = (count) => ({
  state: 'unreadable',
  overlap: true,
  sharp: false,
  similarReadable: false,
  targets: Array.from({ length: count }, (_, index) => ({
    cellId: `cell-${index}`,
    expectedIdentity: 'a'.repeat(64),
    expectedRevision: index + 1,
  })),
});

test('cap rejects the whole queue before writing; every chunk snapshot/key is persisted before sending', async () => {
  const saved = storage();
  assert.throws(() => createReadabilityLabelQueue('g', 'r', payload(10001)));
  assert.equal(saved.size, 0);
  const queue = createReadabilityLabelQueue('g', 'r', payload(10000));
  assert.equal(queue.chunks.length, 40);
  assert.equal(
    new Set(queue.chunks.map((chunk) => chunk.idempotencyKey)).size,
    40,
  );
  const requests = [];
  await drainReadabilityLabelQueue(
    'g',
    async (run, body) => {
      assert.equal(loadReadabilityLabelQueue('g').chunks.length, 40);
      assert.ok(body.targets.length <= 250);
      requests.push(body);
      return { data: {} };
    },
    () => {},
  );
  assert.equal(requests.length, 40);
  assert.equal(loadReadabilityLabelQueue('g'), null);
});

test('409 pauses tail with progress and exact keys/revisions; another command cannot replace it', async () => {
  storage();
  const original = createReadabilityLabelQueue('g', 'r', payload(501));
  const requests = [];
  await assert.rejects(
    drainReadabilityLabelQueue(
      'g',
      async (_, body) => {
        requests.push(body);
        return requests.length === 2
          ? { error: { status: 409 } }
          : { data: {} };
      },
      () => {},
    ),
    /Zapis porcji nie został potwierdzony. Kolejka wstrzymana; ponów zapisane oceny bez zmiany rewizji\./,
  );
  const paused = loadReadabilityLabelQueue('g');
  assert.deepEqual(readabilityQueueProgress(paused), {
    done: 250,
    remaining: 251,
  });
  assert.equal(requests.length, 2);
  assert.throws(() => createReadabilityLabelQueue('g', 'other', payload(300)));
  await assert.rejects(
    drainReadabilityLabelQueue(
      'g',
      async (_, body) => {
        requests.push(body);
        return { error: { status: 409 } };
      },
      () => {},
    ),
  );
  assert.deepEqual(requests[2], original.chunks[1]);
  assert.equal(
    requests.length,
    3,
    'tail never runs after a permanent conflict',
  );
  assert.equal(loadReadabilityLabelQueue('g').completed, 1);
  discardReadabilityLabelQueue('g');
  assert.equal(loadReadabilityLabelQueue('g'), null);
  assert.equal(
    createReadabilityLabelQueue('g', 'other', payload(300)).completed,
    0,
  );
});

test('corrupt queues can only be discarded explicitly and other games/commands remain intact', () => {
  const saved = storage();
  saved.set('readability-label-queue:g', '{broken');
  saved.set('readability-command:other', 'keep');
  saved.set('readability-label-queue:other', 'keep');
  assert.throws(() => loadReadabilityLabelQueue('g'));
  discardReadabilityLabelQueue('g');
  assert.equal(loadReadabilityLabelQueue('g'), null);
  assert.equal(saved.get('readability-command:other'), 'keep');
  assert.equal(saved.get('readability-label-queue:other'), 'keep');
});

test('lost response survives a new Node process and replays the same chunk, then untouched tail', async () => {
  const saved = storage();
  const original = createReadabilityLabelQueue('g', 'r', payload(501));
  const committedKeys = new Set();
  await assert.rejects(
    drainReadabilityLabelQueue(
      'g',
      async (_, body) => {
        committedKeys.add(body.idempotencyKey);
        throw new Error('Lost response');
      },
      () => {},
    ),
  );
  const code = `import {drainReadabilityLabelQueue} from './src/features/readability/readability-label-queue.ts';
    let raw = process.env.QUEUE; const received=[];
    globalThis.window={localStorage:{getItem:()=>raw,setItem:(_,value)=>raw=value,removeItem:()=>raw=null}};
    await drainReadabilityLabelQueue('g',async(run,body)=>{received.push({run,body});return {data:{}}},()=>{});
    process.stdout.write(JSON.stringify({received,raw}));`;
  const child = spawnSync(
    process.execPath,
    ['--experimental-strip-types', '--input-type=module', '-e', code],
    {
      cwd: process.cwd(),
      env: { ...process.env, QUEUE: saved.get('readability-label-queue:g') },
      timeout: 10000,
      encoding: 'utf8',
    },
  );
  assert.equal(child.status, 0, child.stderr);
  const recovered = JSON.parse(child.stdout);
  assert.deepEqual(
    recovered.received.map(({ body }) => body),
    original.chunks,
  );
  for (const { body } of recovered.received)
    committedKeys.add(body.idempotencyKey);
  assert.equal(
    committedKeys.size,
    3,
    'server deduplication sees one key per mutation',
  );
  assert.equal(recovered.raw, null);
});

test('checkpoint storage failure preserves the old key; unmount stops before next chunk', async () => {
  const saved = storage();
  const queue = createReadabilityLabelQueue('g', 'r', payload(300));
  window.localStorage.setItem = () => {
    throw new Error('Quota exceeded');
  };
  await assert.rejects(
    drainReadabilityLabelQueue(
      'g',
      async () => ({ data: {} }),
      () => {},
    ),
    /Quota/,
  );
  assert.equal(loadReadabilityLabelQueue('g').completed, 0);
  window.localStorage.setItem = (key, value) => saved.set(key, value);
  let active = true;
  const calls = [];
  await drainReadabilityLabelQueue(
    'g',
    async (_, body) => {
      calls.push(body);
      active = false;
      return { data: {} };
    },
    () => {},
    () => active,
  );
  assert.deepEqual(calls, [queue.chunks[0]]);
  assert.equal(loadReadabilityLabelQueue('g').completed, 1);
});
