import test from 'node:test';
import assert from 'node:assert/strict';
import { DiagnosticAggregates } from '../src/native/diagnostic-log.ts';
import { DiagnosticLog } from '../src/native/diagnostic-log.ts';
import { mkdir, mkdtemp, readFile } from 'node:fs/promises';
import path from 'node:path';
import { removeOwnedTemp } from '../scripts/release-support.mjs';

test('persisted summaries retain only finite bounded numeric fields, never image data', async () => {
  const root = path.resolve('.tmp');
  await mkdir(root, { recursive: true });
  const fixture = await mkdtemp(path.join(root, 'metric-log-'));
  try {
    await new DiagnosticLog(fixture).write(
      'performance-summary',
      'native-execute-ms',
      {
        count: 1e15,
        sampleCount: 1000,
        median: 1.5,
        p95: NaN,
        maximum: -1,
        path: 'private-photo.jpg',
        imageId: 'private-id',
      },
    );
    const line = JSON.parse(
      await readFile(path.join(fixture, 'selector.log'), 'utf8'),
    );
    assert.equal(line.count, 1e12);
    assert.equal(line.sampleCount, 256);
    assert.equal(line.median, 1.5);
    assert.deepEqual(Object.keys(line).sort(), [
      'code',
      'count',
      'event',
      'median',
      'sampleCount',
      'time',
    ]);
  } finally {
    await removeOwnedTemp(fixture, root);
  }
});

test('performance samples keep last 256, count all, and flush once without affecting operations', async () => {
  const metrics = new DiagnosticAggregates();
  for (let n = 1; n <= 300; n++) metrics.record('native-execute-ms', n);
  metrics.record('native-execute-ms', NaN);
  metrics.record('native-execute-ms', -1);
  assert.deepEqual(metrics.snapshot(), [
    {
      metric: 'native-execute-ms',
      metadata: {
        count: 300,
        sampleCount: 256,
        median: 172,
        p95: 288,
        maximum: 300,
      },
    },
  ]);
  const writes = [];
  await metrics.flush({
    write: async (...args) => {
      writes.push(args);
      throw new Error('disk unavailable');
    },
  });
  assert.equal(writes.length, 1);
  assert.deepEqual(metrics.snapshot(), []);
  metrics.record('photo-open-ms', 1);
  assert.equal(metrics.snapshot()[0].metadata.count, 1);
});
