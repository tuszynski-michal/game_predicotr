import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import {
  DEFAULT_VIEW,
  validateId,
  validateView,
  ViewPreferencesStore,
} from '../src/native/view-preferences.ts';
import { validateCreate } from '../src/native/project-controller.ts';
test('native view cache validates every field and rejects extra paths', () => {
  assert.deepEqual(validateView(DEFAULT_VIEW), DEFAULT_VIEW);
  for (const v of [
    { ...DEFAULT_VIEW, path: 'C:/secret' },
    { ...DEFAULT_VIEW, navigationStep: 11 },
    { ...DEFAULT_VIEW, zoom: 3001 },
    { ...DEFAULT_VIEW, scrollX: -1 },
    { ...DEFAULT_VIEW, scrollY: NaN },
  ])
    assert.throws(() => validateView(v), { code: 'INVALID_ARGUMENT' });
  assert.throws(() => validateId('../project'));
  assert.equal(validateId(randomUUID()).length, 36);
});
test('new project validates numbering and explicit local storage confirmation', () => {
  const valid = {
    firstLayout: 1,
    direction: 'ascending',
    sequenceUpperBound: null,
    customLocations: false,
    localStorageConfirmed: true,
  };
  assert.deepEqual(validateCreate(valid), valid);
  for (const value of [
    { ...valid, firstLayout: 0 },
    { ...valid, direction: 'reverse' },
    { ...valid, localStorageConfirmed: false },
    { ...valid, sourceRoot: 'C:/secret' },
    { ...valid, sequenceUpperBound: 0 },
  ])
    assert.throws(() => validateCreate(value), { code: 'INVALID_ARGUMENT' });
});
test('view writes serialize and survive a new instance; corrupt/missing cache only resets view', async (t) => {
  await mkdir('.tmp', { recursive: true });
  const root = await mkdtemp(path.resolve('.tmp/renderer-cache-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const id = randomUUID();
  const cache = new ViewPreferencesStore(path.join(root, 'views'));
  assert.deepEqual(await cache.load(id), DEFAULT_VIEW);
  const first = cache.save(id, { ...DEFAULT_VIEW, zoom: 200 });
  const final = { navigationStep: 15, zoom: 3000, scrollX: 44, scrollY: 72 };
  const second = cache.save(id, final);
  await Promise.all([first, second]);
  await cache.flush();
  assert.deepEqual(
    await new ViewPreferencesStore(path.join(root, 'views')).load(id),
    final,
  );
  await writeFile(path.join(root, 'views', `${id}.json`), 'corrupt');
  assert.deepEqual(await cache.load(id), DEFAULT_VIEW);
});
