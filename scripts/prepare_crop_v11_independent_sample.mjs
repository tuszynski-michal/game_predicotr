// Read only sources; diagnostic previews are written ONLY to the supplied workspace directory.
import { readdir, readFile, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import sharp from 'sharp';
import { independentCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-independent.mjs';
const deadline = setTimeout(() => process.exit(2), 120000);
try {
  const root = process.argv[2],
    out = path.resolve(process.argv[3]);
  if (!out.startsWith(path.resolve('.tmp') + path.sep))
    throw Error('WORKSPACE_PREVIEW_ONLY');
  const excluded = new Set([
    '70363 - 93861',
    '303319 -326700',
    '45163 - 70371',
    '200575 - 222912',
  ]);
  if (process.argv[4] === 'third')
    for (const ref of independentCropReferences) excluded.add(ref.directory);
  const dirs = (await readdir(root, { withFileTypes: true }))
    .filter(
      (d) =>
        d.isDirectory() && !d.name.includes('cut') && !excluded.has(d.name),
    )
    .sort((a, b) => parseInt(a.name) - parseInt(b.name))
    .slice(0, 10);
  await mkdir(out, { recursive: true });
  const refs = [];
  for (const d of dirs) {
    const files = (await readdir(path.join(root, d.name)))
      .filter((f) => /^seq_\d+-\d+\.jpe?g$/i.test(f))
      .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));
    const fileName = files[Math.floor(files.length / 2)],
      bytes = await readFile(path.join(root, d.name, fileName));
    const canonical = sharp(bytes).rotate();
    const raw = await canonical
      .clone()
      .raw()
      .toBuffer({ resolveWithObject: true });
    refs.push({
      directory: d.name,
      fileName,
      sha256: createHash('sha256').update(bytes).digest('hex'),
      width: raw.info.width,
      height: raw.info.height,
    });
    await canonical
      .resize({ width: 360, height: 640, fit: 'inside' })
      .jpeg()
      .toFile(path.join(out, `${refs.length}.jpg`));
  }
  await writeFile(
    path.join(out, 'sources.json'),
    JSON.stringify(refs, null, 2),
  );
  console.log(JSON.stringify(refs));
} finally {
  clearTimeout(deadline);
}
