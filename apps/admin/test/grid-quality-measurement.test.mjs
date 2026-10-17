import assert from 'node:assert/strict';
import test from 'node:test';
import {
  measurementHardSources,
  measurementJudgments,
  measurementMesh,
  measurementReviewerUrl,
} from '../src/features/model-quality/grid-quality-measurement-state.ts';
import {
  clearMeasurementCommand,
  discardMeasurementCommand,
  measurementCommandKey,
  readMeasurementCommand,
  saveMeasurementCommand,
} from '../src/features/model-quality/grid-quality-measurement-command.ts';

const api = 'http://127.0.0.1:8000',
  game = '11111111-1111-4111-8111-111111111111';
const command = {
  kind: 'capture',
  body: {
    idempotencyKey: '22222222-2222-4222-8222-222222222222',
    seed: 'same seed',
    sampleSize: 100,
    hardSourceIds: [],
  },
};
function storage() {
  const map = new Map();
  return {
    map,
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, value),
    removeItem: (key) => map.delete(key),
  };
}

test('hard sources validate bounded distinct UUIDs; preserve their order', () => {
  assert.deepEqual(
    measurementHardSources(` ${game},\n${command.body.idempotencyKey}`),
    [game, command.body.idempotencyKey],
  );
  assert.deepEqual(measurementHardSources(''), []);
  for (const value of [
    'bad',
    `${game} ${game}`,
    Array(101).fill(game).join(','),
  ])
    assert.throws(() => measurementHardSources(value));
});

test('nine row-major positions never shift a gap or invent a verdict', () => {
  const judgments = measurementJudgments({
    judgments: [
      {
        positionIndex: 8,
        geometry: 'incorrect',
        detection: 'unknown',
        sequence: 'unreviewed',
      },
    ],
  });
  assert.deepEqual(
    judgments.map((item) => item.positionIndex),
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
  );
  assert.equal(judgments[4].geometry, 'unreviewed');
  assert.equal(judgments[8].geometry, 'incorrect');
});

test('overlay uses exact stored rows and columns; unavailable/malformed nodes stay absent', () => {
  assert.deepEqual(
    measurementMesh({
      available: true,
      nodes: [
        [
          { x: 1, y: 2 },
          { x: 7, y: 4 },
        ],
        [
          { x: 2, y: 9 },
          { x: 8, y: 10 },
        ],
      ],
    }),
    ['1,2 7,4', '2,9 8,10', '1,2 2,9', '7,4 8,10'],
  );
  assert.deepEqual(
    measurementMesh({ available: false, nodes: [[{ x: 1, y: 2 }]] }),
    [],
  );
  assert.deepEqual(
    measurementMesh({ available: true, nodes: [[], [{ x: 1, y: 2 }]] }),
    [],
  );
  assert.deepEqual(
    measurementMesh({ available: true, nodes: [[{ x: NaN, y: 2 }]] }),
    [],
  );
});

test('restart preserves exact command and scope; completion only clears matching body', () => {
  const s = storage();
  saveMeasurementCommand(s, api, game, command);
  assert.deepEqual(readMeasurementCommand(s, api, game), command);
  assert.equal(readMeasurementCommand(s, api, 'other'), null);
  assert.throws(() => saveMeasurementCommand(s, api, game, command));
  clearMeasurementCommand(s, api, game, {
    ...command,
    body: { ...command.body, seed: 'changed' },
  });
  assert.deepEqual(readMeasurementCommand(s, api, game), command);
  clearMeasurementCommand(s, api, game, command);
  assert.equal(readMeasurementCommand(s, api, game), null);
});

test('bad JSON and malformed command require archive before discard, including write failures', () => {
  const s = storage(),
    key = measurementCommandKey(api, game);
  s.setItem(key, '{broken');
  assert.throws(() => readMeasurementCommand(s, api, game));
  assert.throws(() => saveMeasurementCommand(s, api, game, command));
  discardMeasurementCommand(s, api, game, false);
  assert.equal(s.getItem(key), '{broken');
  const failing = {
    ...s,
    setItem() {
      throw new Error('full');
    },
  };
  assert.throws(() => discardMeasurementCommand(failing, api, game, true));
  assert.equal(s.getItem(key), '{broken');
  discardMeasurementCommand(s, api, game, true);
  assert.equal(s.getItem(key), null);
  const archive = [...s.map.entries()].find(([k]) =>
    k.startsWith(`${key}:archive:`),
  );
  assert.equal(JSON.parse(archive[1]).raw, '{broken');
  s.setItem(
    key,
    JSON.stringify({
      api,
      game,
      command: { ...command, body: { ...command.body, sampleSize: 0 } },
    }),
  );
  assert.throws(() => readMeasurementCommand(s, api, game));
  s.setItem(
    key,
    JSON.stringify({
      api,
      game,
      command: {
        ...command,
        body: {
          ...command.body,
          idempotencyKey: [command.body.idempotencyKey],
        },
      },
    }),
  );
  assert.throws(() => readMeasurementCommand(s, api, game));
});

test('Reviewer opens its origin without unsupported scope parameters', () => {
  const url = new URL(
    measurementReviewerUrl(
      'http://127.0.0.1:3000/screen?gameId=ignored#ignored',
    ),
  );
  assert.equal(url.port, '3001');
  assert.equal(url.pathname, '/');
  assert.equal(url.search, '');
  assert.equal(url.hash, '');
  assert.equal(measurementReviewerUrl('https://public.example'), null);
});
