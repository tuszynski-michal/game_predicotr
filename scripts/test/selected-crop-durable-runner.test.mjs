import assert from 'node:assert/strict';
import test from 'node:test';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import sharp from 'sharp';
import {
  processCropDirectory,
  renderCropSource,
} from '../lib/selected-crop-durable-runner.mjs';
import { CROP_V11_POLICY } from '../../packages/manual-image-selection-core/src/auto-crop-v11.ts';

test(
  'EXIF 1–8 canonicalized once, full fallback retains 1:1 dimensions and no orientation tag',
  { timeout: 20000 },
  async () => {
    for (let orientation = 1; orientation <= 8; orientation++) {
      const source = await sharp({
        create: { width: 96, height: 160, channels: 3, background: '#333333' },
      })
        .withMetadata({ orientation })
        .jpeg()
        .toBuffer();
      const { proposal, output } = await renderCropSource(
        source,
        CROP_V11_POLICY,
      );
      const expected =
        orientation >= 5
          ? { width: 160, height: 96 }
          : { width: 96, height: 160 };
      assert.deepEqual(
        { width: proposal.crop.width, height: proposal.crop.height },
        expected,
      );
      assert.equal(proposal.structural.status, 'needs_manual_crop');
      const metadata = await sharp(output).metadata();
      assert.equal(metadata.width, expected.width);
      assert.equal(metadata.height, expected.height);
      assert.equal(metadata.orientation, undefined);
    }
  },
);
async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'crop-v11-test-'));
  const source = path.join(root, 'picked');
  await fs.mkdir(source);
  const bytes = await sharp({
    create: { width: 96, height: 160, channels: 3, background: '#333333' },
  })
    .jpeg()
    .toBuffer();
  await fs.writeFile(path.join(source, 'seq_1-9.jpg'), bytes);
  t.after(async () => {
    if (
      path.dirname(root) !== os.tmpdir() ||
      !path.basename(root).startsWith('crop-v11-test-')
    )
      throw new Error('UNSAFE_TEST_CLEANUP');
    await fs.rm(root, { recursive: true });
  });
  return source;
}
for (const phase of ['intent', 'part', 'publish', 'shard'])
  test(
    `restart after ${phase} preserves exactly one verified output`,
    { timeout: 15000 },
    async (t) => {
      const source = await fixture(t);
      await assert.rejects(
        processCropDirectory(source, CROP_V11_POLICY, {
          hook: async (current) => {
            if (current === phase) throw new Error('TEST_CRASH');
          },
        }),
        /TEST_CRASH/,
      );
      let renders = 0;
      const result = await processCropDirectory(source, CROP_V11_POLICY, {
        render: async (...args) => {
          renders++;
          return renderCropSource(...args);
        },
      });
      assert.equal(result.prepared, 1);
      assert.equal(result.failures.length, 0);
      assert.equal(renders, ['publish', 'shard'].includes(phase) ? 0 : 1);
      const manifest = JSON.parse(
        await fs.readFile(
          path.join(source + ' cut', 'manual-image-crop-output-v1.json'),
          'utf8',
        ),
      );
      assert.deepEqual(manifest.reviewedFileNames, []);
      assert.equal(
        manifest.entries[0].result.autoCropProposal.structural.status,
        'needs_manual_crop',
      );
    },
  );
test(
  'changed output is protected on retry and no file is silently skipped',
  { timeout: 15000 },
  async (t) => {
    const source = await fixture(t);
    await processCropDirectory(source, CROP_V11_POLICY);
    const target = path.join(source + ' cut', 'seq_1-9.jpg');
    await fs.writeFile(target, 'foreign');
    const result = await processCropDirectory(source, CROP_V11_POLICY);
    assert.equal(result.failures[0].code, 'CROP_OUTPUT_CHANGED');
    assert.equal(await fs.readFile(target, 'utf8'), 'foreign');
  },
);
test(
  'decode failure is isolated and only the missing source is retried',
  { timeout: 15000 },
  async (t) => {
    const source = await fixture(t);
    await fs.copyFile(
      path.join(source, 'seq_1-9.jpg'),
      path.join(source, 'seq_10-18.jpg'),
    );
    let call = 0;
    const first = await processCropDirectory(source, CROP_V11_POLICY, {
      render: async (...args) => {
        if (call++ === 0) throw new Error('DECODE_FAILED');
        return renderCropSource(...args);
      },
    });
    assert.equal(first.prepared, 1);
    assert.equal(first.failures.length, 1);
    call = 0;
    const second = await processCropDirectory(source, CROP_V11_POLICY, {
      render: async (...args) => {
        call++;
        return renderCropSource(...args);
      },
    });
    assert.equal(second.prepared, 2);
    assert.equal(call, 1);
  },
);
