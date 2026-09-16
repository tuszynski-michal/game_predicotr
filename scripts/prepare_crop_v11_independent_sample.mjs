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
  let dirs = (await readdir(root, { withFileTypes: true }))
    .filter(
      (d) =>
        d.isDirectory() && !d.name.includes('cut') && !excluded.has(d.name),
    )
    .sort((a, b) => parseInt(a.name) - parseInt(b.name));
  if (process.argv[4] === 'fourth') {
    const alternating = dirs.filter((_directory, index) => index % 2 === 0);
    const last = dirs.at(-1);
    const firstOmitted = dirs.find(
      (directory) => !alternating.includes(directory),
    );
    dirs = [
      ...alternating,
      ...(last && !alternating.includes(last) ? [last] : []),
      ...(firstOmitted && !alternating.includes(firstOmitted)
        ? [firstOmitted]
        : []),
    ].slice(0, 10);
  } else if (['fifth', 'sixth'].includes(process.argv[4]))
    dirs = dirs.slice(-10);
  else dirs = dirs.slice(0, 10);
  await mkdir(out, { recursive: true });
  const refs = [];
  for (const d of dirs) {
    const files = (await readdir(path.join(root, d.name)))
      .filter((f) => /^seq_\d+-\d+\.jpe?g$/i.test(f))
      .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));
    const fileName =
        files[
          Math.floor(
            files.length *
              (process.argv[4] === 'fourth'
                ? 0.23
                : process.argv[4] === 'fifth'
                  ? 0.73
                  : process.argv[4] === 'sixth'
                    ? 0.89
                    : 0.5),
          )
        ],
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
    const grid = Array.from({ length: 65 }, (_unused, index) => {
      const y = index * 10;
      return `<path d="M0 ${y}H360" stroke="${index % 2 ? '#ffffff55' : '#00ffff99'}"/><text x="2" y="${Math.min(637, y + 9)}" fill="#fff" stroke="#000" stroke-width="1" font-size="9">${y}</text>`;
    }).join('');
    await canonical
      .resize({ width: 360, height: 640, fit: 'inside' })
      .composite([
        {
          input: Buffer.from(
            `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="640">${grid}</svg>`,
          ),
        },
      ])
      .png()
      .toFile(path.join(out, `${refs.length}-grid.png`));
  }
  await writeFile(
    path.join(out, 'sources.json'),
    JSON.stringify(refs, null, 2),
  );
  console.log(JSON.stringify(refs));
} finally {
  clearTimeout(deadline);
}
