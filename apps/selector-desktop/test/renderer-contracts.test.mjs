import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import path from 'node:path';
import {
  DEFAULT_VIEW,
  validateId,
  validateView,
  ViewPreferencesStore,
} from '../src/native/view-preferences.ts';
import { validateCreate } from '../src/native/project-controller.ts';
import { removeOwnedTemp } from '../scripts/release-support.mjs';
import { SecureFiles } from '../src/filesystem/secure-files.ts';
import { disposeNativeChecks } from '../src/native/windows-check-worker.ts';
import { resolveDesktopShortcut } from '../src/renderer/desktop-shortcuts.ts';
import { DesktopLifecycle } from '../src/native/desktop-lifecycle.ts';
after(() => disposeNativeChecks());
test('desktop decision repeats are consumed without a decision; fresh presses and arrows work', () => {
  for (const [input, action] of [
    [{ key: 'Enter' }, 'accept'],
    [{ key: 'f' }, 'accept'],
    [{ key: 'F' }, 'accept'],
    [{ key: 'Tab' }, 'skip'],
    [{ key: 'z', ctrlKey: true }, 'undo'],
    [{ key: 'z', metaKey: true }, 'undo'],
    [{ key: 'a' }, 'undo'],
  ]) {
    assert.deepEqual(resolveDesktopShortcut({ ...input, repeat: true }), {
      action: null,
      preventDefault: true,
    });
    assert.deepEqual(resolveDesktopShortcut({ ...input, repeat: false }), {
      action,
      preventDefault: true,
    });
  }
  for (const [key, action] of [
    ['ArrowLeft', 'previous_image'],
    ['ArrowRight', 'next_image'],
    ['ArrowUp', 'previous_step'],
    ['ArrowDown', 'next_step'],
  ])
    assert.deepEqual(resolveDesktopShortcut({ key, repeat: true }), {
      action,
      preventDefault: true,
    });
  for (const tagName of ['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA'])
    assert.deepEqual(
      resolveDesktopShortcut({ key: 'Tab', repeat: true, target: { tagName } }),
      { action: null, preventDefault: false },
    );
  assert.deepEqual(
    resolveDesktopShortcut({ key: 'f', repeat: true, ctrlKey: true }),
    {
      action: null,
      preventDefault: false,
    },
  );
});

test('second instance focuses normally and schedules exactly one deferred relaunch during close', () => {
  const lifecycle = new DesktopLifecycle();
  assert.equal(lifecycle.secondInstance(), 'focus');
  lifecycle.beginClosing();
  assert.equal(lifecycle.secondInstance(), 'relaunch');
  lifecycle.beginClosing();
  for (let i = 0; i < 5; i++)
    assert.equal(lifecycle.secondInstance(), 'pending');
});
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
  t.after(() => removeOwnedTemp(root, path.resolve('.tmp')));
  const id = randomUUID();
  const cache = new ViewPreferencesStore(path.join(root, 'views'));
  assert.deepEqual(await cache.load(id), DEFAULT_VIEW);
  const first = cache.save(id, { ...DEFAULT_VIEW, zoom: 200 });
  const final = { navigationStep: 15, zoom: 3000, scrollX: 44, scrollY: 72 };
  const second = cache.save(id, final);
  assert.equal(first, second);
  await Promise.all([first, second]);
  await cache.flush();
  assert.deepEqual(
    await new ViewPreferencesStore(path.join(root, 'views')).load(id),
    final,
  );
  await writeFile(path.join(root, 'views', `${id}.json`), 'corrupt');
  assert.deepEqual(await cache.load(id), DEFAULT_VIEW);
});

test('scroll burst coalesces one pending write and close flush preserves the final view', async (t) => {
  await mkdir('.tmp', { recursive: true });
  const root = await mkdtemp(path.resolve('.tmp/renderer-debounce-'));
  t.after(() => removeOwnedTemp(root, path.resolve('.tmp')));
  const cache = new ViewPreferencesStore(path.join(root, 'views'));
  let writes = 0;
  const replace = SecureFiles.prototype.replace;
  SecureFiles.prototype.replace = async function (...args) {
    writes++;
    return replace.apply(this, args);
  };
  t.after(() => {
    SecureFiles.prototype.replace = replace;
  });
  const id = randomUUID();
  const first = cache.save(id, { ...DEFAULT_VIEW, zoom: 1000 });
  let final;
  for (let i = 0; i < 50; i++) {
    final = { ...DEFAULT_VIEW, zoom: 1000, scrollX: i, scrollY: i * 2 };
    assert.equal(cache.save(id, final), first);
  }
  assert.equal(writes, 0);
  await cache.flush();
  await first;
  assert.equal(writes, 1);
  assert.deepEqual(
    await new ViewPreferencesStore(path.join(root, 'views')).load(id),
    final,
  );
});
