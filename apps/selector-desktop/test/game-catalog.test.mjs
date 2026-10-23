import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { GameCatalog } from '../src/native/game-catalog.ts';
import { validateGameUpdate } from '../src/contracts.ts';
import { validateCreate } from '../src/native/project-controller.ts';
import { disposeNativeChecks } from '../src/native/windows-check-worker.ts';
import { removeOwnedTemp } from '../scripts/release-support.mjs';

after(() => disposeNativeChecks());
async function fixture(t) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'game-catalog-'));
  t.after(() => removeOwnedTemp(root, base));
  return root;
}
test('catalog serializes additions, retains more than ten games and survives a new process', async (t) => {
  const root = await fixture(t);
  const catalog = new GameCatalog(root);
  assert.deepEqual(await catalog.list(), []);
  await Promise.all(
    Array.from({ length: 12 }, (_, i) => catalog.add(`Gra ${i}`)),
  );
  await catalog.add('  Mumie  ');
  await catalog.add('mumie');
  const names = await catalog.list();
  assert.equal(names.length, 13);
  assert.ok(names.includes('Mumie'));
  assert.ok(names.includes('Gra 0'));
  const child = spawnSync(
    process.execPath,
    [
      '--experimental-strip-types',
      '--input-type=module',
      '-e',
      `
    import { GameCatalog } from './src/native/game-catalog.ts';
    import { disposeNativeChecks } from './src/native/windows-check-worker.ts';
    try { console.log(JSON.stringify(await new GameCatalog(process.argv[1]).list())); }
    finally { await disposeNativeChecks(); }
  `,
      root,
    ],
    { encoding: 'utf8', timeout: 20000, windowsHide: true },
  );
  assert.equal(child.status, 0, child.stderr);
  assert.deepEqual(JSON.parse(child.stdout), names);
});
test('corrupt catalog is reported and never replaced; failed additions do not poison its queue', async (t) => {
  const root = await fixture(t);
  const file = path.join(root, 'selector-games-v1.json');
  const catalog = new GameCatalog(root);
  for (const invalid of [
    'broken',
    '{"schemaVersion":2,"games":[]}',
    '{"schemaVersion":1,"games":["Mumie","mumie"]}',
  ]) {
    await writeFile(file, invalid);
    await assert.rejects(catalog.add('777'), { code: 'GAME_CATALOG_CORRUPT' });
    assert.equal(await readFile(file, 'utf8'), invalid);
  }
  await writeFile(file, '{"schemaVersion":1,"games":[]}');
  assert.deepEqual(await catalog.add('777'), ['777']);
  for (const invalid of ['', ' ', 'a'.repeat(81), 'Mumie\n', 777])
    assert.throws(() => catalog.add(invalid), { code: 'INVALID_ARGUMENT' });
});
test('updates require an exact a-number or z_a-number at the native boundary', () => {
  const request = {
    firstLayout: 1,
    direction: 'ascending',
    sequenceUpperBound: null,
    customLocations: false,
    localStorageConfirmed: true,
  };
  for (const valid of [
    'a0',
    'a1',
    'a00023',
    'z_a2',
    'z_a9999999999999999999999999999',
  ]) {
    assert.equal(validateGameUpdate(valid), valid);
    assert.equal(
      validateCreate({ ...request, gameUpdate: valid }).gameUpdate,
      valid,
    );
  }
  for (const invalid of [
    undefined,
    null,
    '',
    'a',
    'z_a',
    'A1',
    'Z_a1',
    'a-1',
    'a1b',
    '1a',
    'a1.2',
    'a 1',
    ' a1',
    'a1 ',
    'a1\n',
    'z_a١',
    1,
  ]) {
    assert.throws(() => validateGameUpdate(invalid), {
      code: 'INVALID_ARGUMENT',
    });
    assert.throws(() => validateCreate({ ...request, gameUpdate: invalid }), {
      code: 'INVALID_ARGUMENT',
    });
  }
});
