import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdir,
  readFile,
  writeFile,
  readdir,
  stat,
  utimes,
} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

// Run each phase through run-bounded.mjs 120. There is no implicit cleanup:
// evidence and owned fixtures remain available after a failure.
const workspace = path.resolve(
  fileURLToPath(new URL('../../..', import.meta.url)),
);
const [phase, runName = 'final-20261012'] = process.argv.slice(2);
if (!/^[a-zA-Z0-9_-]+$/.test(runName)) throw new Error('Unsafe run name');
const runRoot = path.join(workspace, '.tmp', 'selector-measurements', runName);
const resultRoot = path.join(
  workspace,
  'artifacts',
  'selector-measurements',
  runName,
);
const configurationPath = path.join(resultRoot, 'configuration.json');
const baseline = 'c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f';
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const jpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+aPoD//Z',
  'base64',
);
const git = (...args) => {
  const result = spawnSync('git', args, {
    cwd: workspace,
    timeout: 10000,
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.status !== 0)
    throw result.error ?? new Error(result.stderr.toString());
  return result.stdout;
};
async function fixtureProof(config) {
  const names = (await readdir(config.fixtureRoot)).sort();
  assert.equal(names.length, 15000);
  const entries = [];
  // Bounded concurrency avoids measuring a synthetic flood of file handles.
  for (let i = 0; i < names.length; i += 32) {
    entries.push(
      ...(await Promise.all(
        names.slice(i, i + 32).map(async (name) => {
          const target = path.join(config.fixtureRoot, name);
          const info = await stat(target);
          assert.equal(hash(await readFile(target)), config.jpegSha256);
          return {
            name,
            sizeBytes: info.size,
            mtimeMs: info.mtimeMs,
            sha256: config.jpegSha256,
          };
        }),
      )),
    );
  }
  return entries;
}
if (phase === 'prepare') {
  // mkdir without recursive at the leaf prevents silently reusing prior data.
  await mkdir(path.dirname(runRoot), { recursive: true });
  await mkdir(runRoot);
  await mkdir(resultRoot, { recursive: true });
  const current = git('rev-parse', 'HEAD').toString().trim();
  assert.equal(
    git('diff', baseline, current, '--', 'packages/manual-image-selection-core')
      .length,
    0,
  );
  const fixtureRoot = path.join(runRoot, 'source');
  await mkdir(fixtureRoot);
  const sources = {},
    provenance = {};
  for (const [version, commit] of [
    ['baseline', baseline],
    ['current', current],
  ]) {
    const destination = path.join(runRoot, version, 'runtime');
    const files = git(
      'ls-tree',
      '-r',
      '--name-only',
      commit,
      '--',
      'apps/selector-desktop/src',
    )
      .toString()
      .trim()
      .split('\n');
    const sourceHashes = [];
    for (const name of files) {
      const bytes = git('show', `${commit}:${name}`);
      const target = path.join(
        destination,
        path.relative('apps/selector-desktop', name),
      );
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, bytes);
      sourceHashes.push({ path: name, sha256: hash(bytes) });
    }
    await writeFile(
      path.join(destination, 'package.json'),
      '{"type":"module"}\n',
    );
    sources[version] = path.join(destination, 'src');
    provenance[version] = {
      sourceCommit: commit,
      sourceHashes,
      sourceTreeSha256: hash(JSON.stringify(sourceHashes)),
    };
  }
  const config = {
    runRoot,
    resultRoot,
    fixtureRoot,
    sources,
    provenance,
    jpegSha256: hash(jpeg),
    jpegBytes: jpeg.length,
    count: 15000,
    createdAt: new Date().toISOString(),
    hardware: {
      platform: process.platform,
      osRelease: os.release(),
      osVersion: os.version(),
      cpu: os.cpus()[0].model,
      logicalCpus: os.cpus().length,
      ramBytes: os.totalmem(),
      node: process.version,
      storageRoot: path.parse(runRoot).root,
      storageLocality:
        'Owned workspace on local Windows fixed drive; production drive check required during create.',
      jpegDescription:
        'Valid Pillow generated 8x8 RGB JPEG, quality80; no representative camera-image decoding or UI rendering measurement.',
    },
  };
  for (let i = 1; i <= config.count; i += 32) {
    await Promise.all(
      Array.from(
        { length: Math.min(32, config.count - i + 1) },
        async (_, offset) => {
          const name = path.join(fixtureRoot, `photo${i + offset}.jpg`);
          await writeFile(name, jpeg);
          await utimes(name, 1700000000.123, 1700000000.123);
        },
      ),
    );
  }
  await writeFile(configurationPath, `${JSON.stringify(config, null, 2)}\n`);
  await writeFile(
    path.join(resultRoot, 'original-proof.json'),
    `${JSON.stringify(await fixtureProof(config))}\n`,
  );
  console.log(
    `Prepared 15000 owned JPEGs (${jpeg.length} bytes each), source snapshots ${baseline} / ${current}`,
  );
} else {
  const config = JSON.parse(await readFile(configurationPath, 'utf8'));
  if (phase === 'verify-source') {
    const expected = JSON.parse(
      await readFile(path.join(resultRoot, 'original-proof.json'), 'utf8'),
    );
    assert.deepEqual(await fixtureProof(config), expected);
    await writeFile(
      path.join(resultRoot, 'source-verification.json'),
      `${JSON.stringify({ unchanged: true, count: 15000, allBytesAndMtimesChecked: true, checkedAt: new Date().toISOString(), nodePid: process.pid })}\n`,
    );
    console.log(
      'PASS: all 15000 original file hashes, sizes and mtimes unchanged in a fresh process.',
    );
  } else if (phase === 'summary') {
    const ledgerRoot = path.join(config.runRoot, 'current', 'project');
    const ledger = await readFile(
      path.join(ledgerRoot, 'selector-operations-v2.jsonl'),
    );
    assert.deepEqual(
      await readFile(
        path.join(ledgerRoot, 'selector-operations-v2.backup.jsonl'),
      ),
      ledger,
    );
    let verifiedLedgerPrefixes = 0;
    const results = {};
    for (const version of ['baseline', 'current']) {
      results[version] = {};
      for (const step of [
        'create',
        'nav',
        'accept',
        'skip',
        'reopen',
        'projection',
      ]) {
        const value = JSON.parse(
          await readFile(
            path.join(resultRoot, `${version}-${step}.json`),
            'utf8',
          ),
        );
        if (version === 'current') {
          for (const files of [value.metadataBefore, value.metadataAfter]) {
            for (const entry of files.filter((entry) =>
              /^selector-operations-v2(?:\.backup)?\.jsonl$/.test(entry.name),
            )) {
              assert.equal(hash(ledger.subarray(0, entry.bytes)), entry.sha256);
              verifiedLedgerPrefixes++;
            }
          }
        }
        const {
          samples: _samples,
          metadataBefore: _before,
          ...compact
        } = value;
        void _samples;
        void _before;
        results[version][step] = compact;
      }
    }
    const summary = {
      config,
      results,
      ledgerEvidence: {
        identicalMirrors: true,
        verifiedLedgerPrefixes,
        finalBytesPerMirror: ledger.length,
        appendPreservedAllMeasuredPrefixes: true,
      },
      sourceVerification: JSON.parse(
        await readFile(
          path.join(resultRoot, 'source-verification.json'),
          'utf8',
        ),
      ),
      limitations: [
        '100 unique operations per version, with 20 NAV, 20 accept/undo pairs and 20 skip/undo pairs. Each category has a separately measured fresh-process open.',
        'OS filesystem caches are not flushed. Cold means fresh Node process and worker, not a physical cold disk.',
        'Checkpoint durations include the measurement checkpoint callback and one journal stat per operation. Preview metric is an ordinary filesystem read of a tiny valid JPEG, excludes protocol/security checks, decoding and UI.',
        'Source IPC still carries O(N) metadata; full manifest remains O(D); cold open validation and retained memory remain O(N+R+D). No universal hardware, power-loss or realistic-JPEG guarantee.',
      ],
    };
    await writeFile(
      path.join(resultRoot, 'summary.json'),
      `${JSON.stringify(summary, null, 2)}\n`,
    );
    console.log(
      JSON.stringify(
        {
          resultRoot,
          baselineNav: results.baseline.nav.operationTiming,
          currentNav: results.current.nav.operationTiming,
          currentWarmWorkerSpawns: ['nav', 'accept', 'skip'].map(
            (key) => results.current[key].warmWorkerSpawnDelta,
          ),
          unchangedSource: summary.sourceVerification.unchanged,
        },
        null,
        2,
      ),
    );
  } else {
    const match =
      /^(baseline|current)-(create|nav|accept|skip|reopen|projection)$/.exec(
        phase ?? '',
      );
    if (!match)
      throw new Error(
        'Usage: measure-selector.mjs prepare|<baseline|current>-<create|nav|accept|skip|reopen>|verify-source|summary [owned-run-name]',
      );
    const worker = fileURLToPath(
      new URL('./measurement-worker.mjs', import.meta.url),
    );
    const result = spawnSync(
      process.execPath,
      [
        fileURLToPath(new URL('./run-bounded.mjs', import.meta.url)),
        '110',
        process.execPath,
        '--experimental-strip-types',
        worker,
        configurationPath,
        match[1],
        match[2],
      ],
      { cwd: workspace, stdio: 'inherit', timeout: 115000, windowsHide: true },
    );
    if (result.status !== 0)
      throw (
        result.error ?? new Error(`Measurement worker failed: ${result.status}`)
      );
  }
}
