import { waitForHistory, continueFromHistory } from './ui-smoke-support.mjs';
import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import {
  mkdir,
  mkdtemp,
  readFile,
  writeFile,
  cp,
  readdir,
  stat,
} from 'node:fs/promises';
import path from 'node:path';
import { hashFile, createOwnedSmoke } from './release-support.mjs';
import { verifyExtractedRelease } from './verify-release.mjs';

const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const fixture = await mkdtemp(path.join(tempRoot, 'update-smoke-'));
const source = path.join(fixture, 'source');
const oldUserData = path.join(fixture, 'old-user-data');
const newUserData = path.join(fixture, 'new-user-data');
const oldReaderUserData = path.join(fixture, 'old-reader-user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-update',
  fixture,
  tempRoot,
  userData: [oldUserData, newUserData, oldReaderUserData],
});
let application;
let page;
async function select(directory) {
  await application.evaluate(({ dialog }, value) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [value],
    });
    dialog.showMessageBox = async () => ({
      response: 1,
      checkboxChecked: false,
    });
  }, directory);
}
async function launch(program, version, userData) {
  application = await smoke.launch(electron, {
    executablePath: path.join(program, 'Selektor-zdjec.exe'),
    args: [`--user-data-dir=${userData}`],
    timeout: 20000,
  });
  assert.deepEqual(
    await application.evaluate(({ app }) => [
      app.getVersion(),
      app.getPath('userData'),
    ]),
    [version, userData],
  );
  page = await application.firstWindow({ timeout: 20000 });
  page.setDefaultTimeout(20000);
}
async function snapshot() {
  const result = await page.evaluate(() => window.selector.snapshot());
  assert.equal(result.ok, true);
  return result.value;
}
function cursor(value) {
  const ordinal = value.source.images.findIndex(
    (image) => image.id === value.currentImageId,
  );
  assert.ok(ordinal >= 0);
  return { ordinal, relativePath: value.source.images[ordinal].relativePath };
}
async function persistedCursor(project) {
  const envelope = JSON.parse(
    await readFile(path.join(project, 'selector-project-v1.json'), 'utf8'),
  );
  const value = envelope.value;
  assert.ok(value.schemaVersion === 1 || value.schemaVersion === 2);
  const currentRelativePath =
    value.schemaVersion === 2
      ? value.scalar.currentRelativePath
      : value.currentRelativePath;
  assert.equal(typeof currentRelativePath, 'string');
  return currentRelativePath;
}
async function waitState(predicate) {
  const deadline = Date.now() + 20000;
  do {
    const value = await snapshot();
    if (predicate(value)) return value;
    await new Promise((resolve) => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  throw new Error('Update state did not settle');
}
async function imageReady() {
  await page.waitForFunction(() => {
    const image = document.querySelector('.preview img');
    return image?.complete && image.naturalWidth === 800;
  });
}
async function close() {
  await page
    .getByRole('button', { name: 'Zamknij projekt', exact: true })
    .click();
  await waitForHistory(page);
  await smoke.close(application);
  application = null;
}
async function tree(directory) {
  const result = [];
  async function walk(current) {
    for (const entry of (await readdir(current, { withFileTypes: true })).sort(
      (a, b) => a.name.localeCompare(b.name),
    )) {
      const file = path.join(current, entry.name);
      assert.equal(entry.isSymbolicLink(), false);
      if (entry.isDirectory()) await walk(file);
      else {
        const info = await stat(file);
        result.push([
          path.relative(directory, file),
          info.size,
          info.mtimeMs,
          await hashFile(file),
        ]);
      }
    }
  }
  await walk(directory);
  return result;
}
try {
  await smoke.run(async () => {
    const currentVersion = JSON.parse(
      await readFile('package.json', 'utf8'),
    ).version;
    const positional = process.argv
      .slice(2)
      .filter((arg) => !arg.startsWith('--'));
    const oldArchiveOption = process.argv
      .find((arg) => arg.startsWith('--old-archive='))
      ?.slice('--old-archive='.length);
    const archives = [
      path.resolve(
        oldArchiveOption ??
          positional[0] ??
          'out/releases/pilot-0.1.0-abe8e645/Selektor zdjec-win32-x64-0.1.0.zip',
      ),
      path.resolve(
        positional[1] ??
          `out/make/zip/win32/x64/Selektor zdjec-win32-x64-${currentVersion}.zip`,
      ),
    ];
    const versions = [];
    const programs = [];
    for (const [index, archive] of archives.entries()) {
      const metadata = JSON.parse(
        await readFile(`${archive}.release.json`, 'utf8'),
      );
      if (index === 0)
        assert.ok(
          ['0.1.0', '0.1.2', '1.0.3'].includes(metadata.applicationVersion),
        );
      else assert.equal(metadata.applicationVersion, currentVersion);
      versions.push(metadata.applicationVersion);
      assert.equal(metadata.applicationSourceDirty, false);
      assert.equal(metadata.bytes, (await stat(archive)).size);
      assert.equal(metadata.sha256, await hashFile(archive));
      assert.equal(
        await readFile(`${archive}.sha256`, 'utf8'),
        `${metadata.sha256}  ${path.basename(archive)}\n`,
      );
      const program = path.join(fixture, `program-${index}`);
      execFileSync(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          'Expand-Archive -LiteralPath $env:SELECTOR_ARCHIVE -DestinationPath $env:SELECTOR_PROGRAM -ErrorAction Stop',
        ],
        {
          env: {
            ...process.env,
            SELECTOR_ARCHIVE: archive,
            SELECTOR_PROGRAM: program,
          },
          timeout: 30000,
          windowsHide: true,
        },
      );
      assert.equal(
        await hashFile(path.join(program, 'resources/app.asar')),
        metadata.appAsarSha256,
      );
      await verifyExtractedRelease(program, metadata);
      programs.push(program);
    }
    await mkdir(source);
    await launch(programs[0], versions[0], oldUserData);
    const jpeg = await application.evaluate(({ nativeImage }) =>
      nativeImage
        .createFromBitmap(Buffer.alloc(800 * 600 * 4, 180), {
          width: 800,
          height: 600,
        })
        .toJPEG(80)
        .toString('base64'),
    );
    for (let index = 1; index <= 3; index++)
      await writeFile(
        path.join(source, `photo${index}.jpg`),
        Buffer.from(jpeg, 'base64'),
      );
    await select(source);
    if (versions[0] === '0.1.0') {
      await page
        .getByRole('button', { name: 'Nowy projekt', exact: true })
        .click();
      await page.getByLabel('Ostatnia plansza', { exact: true }).fill('30');
      const localConfirmation = page.getByRole('checkbox', {
        name: /Projekt i wynik będą/,
      });
      if (await localConfirmation.count()) await localConfirmation.check();
      await page
        .getByRole('button', { name: 'Wybierz zdjęcia i utwórz projekt' })
        .click();
    } else {
      await page
        .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
        .click();
      await page.getByLabel('Nazwa gry', { exact: true }).fill('Smoke update');
      if (await page.getByLabel('Aktualizacja', { exact: true }).count())
        await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
      await page.getByLabel('Ostatnia plansza', { exact: true }).fill('30');
      const localConfirmation = page.getByRole('checkbox', {
        name: /Projekt i wynik będą/,
      });
      if (await localConfirmation.count()) await localConfirmation.check();
      await page
        .getByRole('button', { name: 'Rozpocznij wybieranie', exact: true })
        .click();
    }
    await imageReady();
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
      .click();
    await waitState((value) => value.acceptedCount === 1);
    // The native commit can precede React's response and busy=false render.
    // A key sent during that interval is intentionally ignored by the old UI.
    await imageReady();
    await page.waitForFunction(
      () =>
        document
          .querySelector('[data-testid="counts"]')
          ?.textContent.includes('Wybrane: 1') &&
        document.querySelector('main')?.getAttribute('aria-busy') === 'false',
    );
    assert.equal(
      await page
        .getByRole('button', { name: /^Pomiń(?: zakres)?(?: \(Tab\))?$/ })
        .isEnabled(),
      true,
    );
    await page.locator('h1').click();
    await page.keyboard.press('Tab');
    await waitState((value) => value.skippedCount === 1);
    // Historical UI drops arrows while its native skip response is pending.
    // Snapshot can see the store commit before the renderer releases busy.
    await page.waitForFunction(
      () =>
        document
          .querySelector('[data-testid="counts"]')
          ?.textContent.includes('Pominięte zakresy: 1') &&
        document.querySelector('main')?.getAttribute('aria-busy') === 'false' &&
        [...document.querySelectorAll('button')].find((button) =>
          /^Pomiń(?: zakres)?(?: \(Tab\))?$/.test(button.textContent.trim()),
        )?.disabled === false,
    );
    await page.locator('h1').click();
    await page.keyboard.press('ArrowRight');
    const old = await waitState(
      (value) =>
        value.source.images.findIndex(
          (image) => image.id === value.currentImageId,
        ) === 2,
    );
    assert.equal(old.nextRangeStart, 19);
    await close();
    const project = `${source} selekcja`;
    const output =
      versions[0] === '1.0.3'
        ? path.join(fixture, 'Smoke update a1 1-30')
        : `${source} wybrane`;
    const oldCursor = cursor(old);
    assert.deepEqual(oldCursor, { ordinal: 2, relativePath: 'photo3.jpg' });
    assert.equal(await persistedCursor(project), oldCursor.relativePath);
    const oldAcceptedHash = await hashFile(path.join(output, 'seq_1-9.jpg'));
    const originals = await Promise.all([
      tree(source),
      tree(project),
      tree(output),
    ]);
    const copiedProject = path.join(fixture, 'copied-project');
    const copiedOutput = path.join(fixture, 'copied-output');
    await cp(project, copiedProject, {
      recursive: true,
      errorOnExist: true,
      force: false,
    });
    await cp(output, copiedOutput, {
      recursive: true,
      errorOnExist: true,
      force: false,
    });
    await launch(programs[1], currentVersion, newUserData);
    await select(copiedProject);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await imageReady();
    const opened = await snapshot();
    assert.equal(opened.projectId, old.projectId);
    assert.equal(opened.acceptedCount, 1);
    assert.equal(opened.skippedCount, 1);
    assert.equal(opened.nextRangeStart, 19);
    assert.deepEqual(cursor(opened), oldCursor);
    assert.equal(await persistedCursor(copiedProject), oldCursor.relativePath);
    assert.equal(
      await hashFile(path.join(copiedOutput, 'seq_1-9.jpg')),
      oldAcceptedHash,
    );
    await page
      .locator('summary', { hasText: 'Inne lokalizacje źródła i wyniku' })
      .click();
    await select(copiedOutput);
    await page
      .getByRole('button', { name: 'Wskaż ponownie wynik', exact: true })
      .click();
    await waitState((value) => value.outputName === 'copied-output');
    await page
      .getByRole('button', { name: 'Wybierz (Enter / F)', exact: true })
      .click();
    const advanced = await waitState(
      (value) => value.acceptedCount === 2 && value.nextRangeStart === 28,
    );
    await imageReady();
    await close();
    await launch(programs[1], currentVersion, newUserData);
    await select(copiedProject);
    await continueFromHistory(page);
    await imageReady();
    const continued = await snapshot();
    assert.equal(continued.acceptedCount, 2);
    assert.equal(continued.skippedCount, 1);
    assert.deepEqual(cursor(continued), cursor(advanced));
    assert.equal(
      await persistedCursor(copiedProject),
      cursor(advanced).relativePath,
    );
    assert.equal(continued.nextRangeStart, 28);
    assert.equal(
      await hashFile(path.join(copiedOutput, 'seq_1-9.jpg')),
      oldAcceptedHash,
    );
    const photoHash = await hashFile(path.join(source, 'photo3.jpg'));
    assert.equal(
      await hashFile(path.join(copiedOutput, 'seq_19-27.jpg')),
      photoHash,
    );
    await close();
    // Exercise the genuine historical reader against our migrated copy only.
    // Include every authoritative file and its mtime; a transient reader lock
    // must be released before comparison and cannot hide any data mutation.
    for (const file of [
      'selector-project-v1.json',
      'selector-project-v1.backup.json',
    ]) {
      assert.equal(
        JSON.parse(await readFile(path.join(copiedProject, file), 'utf8')).value
          .schemaVersion,
        2,
      );
    }
    const migratedFiles = await Promise.all([
      tree(copiedProject),
      tree(copiedOutput),
    ]);
    if (versions[0] !== '1.0.3') {
      await launch(programs[0], versions[0], oldReaderUserData);
      await select(copiedProject);
      // Both verified historical preload contracts expose open() without args.
      const refused = await page.evaluate(() => window.selector.open());
      assert.equal(refused.ok, false);
      assert.equal(refused.error.code, 'UNSUPPORTED_PROJECT_SCHEMA');
      await smoke.close(application);
      application = null;
      assert.deepEqual(
        await Promise.all([tree(copiedProject), tree(copiedOutput)]),
        migratedFiles,
      );
      console.log(
        `PASS: historical EXE ${versions[0]} refuses migrated head2 with UNSUPPORTED_PROJECT_SCHEMA; project/output bytes and mtimes unchanged.`,
      );
    }
    assert.deepEqual(
      await Promise.all([tree(source), tree(project), tree(output)]),
      originals,
    );
    console.log(
      `PASS: actual ZIP versions ${versions[0]} → ${currentVersion}; copied project decisions/cursor/JPEG retained, explicit copied-output relink, continued decisions survive new process, original fixture files unchanged.`,
    );
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
