import { promises as fs } from 'node:fs';
import path from 'node:path';

import sharp from 'sharp';

import { CROP_V11_POLICY } from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import {
  CROP_V12_POLICY,
  fourPointAnchorFromStructuralEvidence,
} from '../packages/manual-image-selection-core/src/auto-crop-v12-registration.ts';
import {
  renderCropSource,
  sha256,
} from './lib/selected-crop-durable-runner.mjs';

const [
  sourceArgument,
  outputArgument,
  startArgument = '0',
  countArgument = '20',
] = process.argv.slice(2);
if (!sourceArgument || !outputArgument)
  throw new Error('Usage: <source-directory> <output.png> [start] [count]');

const source = path.resolve(sourceArgument);
const output = path.resolve(outputArgument);
const start = Number(startArgument);
const count = Number(countArgument);
const sequenceStart = (name) => Number(/^seq_(\d+)-/.exec(name)?.[1] ?? NaN);
const allFiles = (await fs.readdir(source))
  .filter((name) => /^seq_\d+-\d+\.jpe?g$/i.test(name))
  .sort((left, right) => sequenceStart(left) - sequenceStart(right));
const files = allFiles.slice(start, start + count);

let anchor = null;
const explicitAnchor = process.argv
  .find((argument) => argument.startsWith('--anchor='))
  ?.slice('--anchor='.length);
const bootstrapCandidates = explicitAnchor
  ? [explicitAnchor]
  : [
      ...allFiles.slice(start, start + Math.max(count, 8)),
      ...Array.from(
        { length: 6 },
        (_, index) =>
          allFiles[Math.min(allFiles.length - 1, start + (index + 1) * 100)],
      ).filter(Boolean),
    ];
for (const fileName of [...new Set(bootstrapCandidates)]) {
  const bytes = await fs.readFile(path.join(source, fileName));
  const rendered = await renderCropSource(bytes, CROP_V11_POLICY);
  if (rendered.proposal.structural?.status !== 'detected') continue;
  anchor = {
    bytes,
    descriptor: fourPointAnchorFromStructuralEvidence({
      sourceName: fileName,
      sourceChecksumSha256: sha256(bytes),
      evidence: rendered.proposal.structural,
    }),
  };
  break;
}
const tiles = [];
for (const fileName of files) {
  const bytes = await fs.readFile(path.join(source, fileName));
  const rendered = await renderCropSource(bytes, CROP_V12_POLICY, anchor);
  const method =
    rendered.proposal.registration?.status === 'registered'
      ? 'anchor'
      : rendered.proposal.structural?.status === 'detected'
        ? 'structural'
        : 'manual';
  const image = await sharp(rendered.output)
    .resize({ width: 220, height: 300, fit: 'contain', background: '#111827' })
    .extend({
      top: 28,
      background: method === 'manual' ? '#7f1d1d' : '#064e3b',
    })
    .composite([
      {
        input: Buffer.from(
          `<svg width="220" height="28"><text x="8" y="19" fill="white" font-size="12">${fileName} · ${method}</text></svg>`,
        ),
        top: 0,
        left: 0,
      },
    ])
    .png()
    .toBuffer();
  tiles.push(image);
  if (rendered.proposal.structural?.status === 'detected')
    anchor = {
      bytes,
      descriptor: fourPointAnchorFromStructuralEvidence({
        sourceName: fileName,
        sourceChecksumSha256: sha256(bytes),
        evidence: rendered.proposal.structural,
      }),
    };
}

const columns = 4;
const tileWidth = 220;
const tileHeight = 328;
const rows = Math.ceil(tiles.length / columns);
await fs.mkdir(path.dirname(output), { recursive: true });
await sharp({
  create: {
    width: columns * tileWidth,
    height: rows * tileHeight,
    channels: 3,
    background: '#030712',
  },
})
  .composite(
    tiles.map((input, index) => ({
      input,
      left: (index % columns) * tileWidth,
      top: Math.floor(index / columns) * tileHeight,
    })),
  )
  .png()
  .toFile(output);
process.stdout.write(`${JSON.stringify({ output, files: files.length })}\n`);
