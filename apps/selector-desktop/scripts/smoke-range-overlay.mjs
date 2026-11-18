import { _electron as electron } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createOwnedSmoke } from './release-support.mjs';
import { continueFromHistory } from './ui-smoke-support.mjs';

await mkdir('.tmp', { recursive: true });
const root = await mkdtemp(path.resolve('.tmp/overlay-smoke-'));
const source = path.join(root, 'source');
const userData = path.join(root, 'user-data');
const local = process.argv.includes('--local');
const smoke = createOwnedSmoke({
  name: 'smoke-range-overlay',
  fixture: root,
  tempRoot: path.resolve('.tmp'),
  userData: [userData],
});
let application;
async function launch() {
  application = await smoke.launch(electron, {
    executablePath: local
      ? (await import('electron')).default
      : path.resolve(process.argv[2]),
    args: [...(local ? ['.'] : []), `--user-data-dir=${userData}`],
    timeout: 20000,
  });
  const page = await application.firstWindow();
  page.setDefaultTimeout(10000);
  return page;
}
async function ready(page) {
  await page.waitForFunction(() => {
    const img = document.querySelector('.preview-image-host img');
    return (
      img?.complete &&
      img.naturalWidth > 0 &&
      !document.querySelector('.image-loading')
    );
  });
}
async function overlayState(page) {
  return page.evaluate(
    async () => (await window.selector.snapshot()).value.view.rangeOverlay,
  );
}
async function drag(page, locator, dx, dy) {
  const box = await locator.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 5 });
  await page.mouse.up();
}
try {
  await smoke.run(async () => {
    await mkdir(source);
    let page = await launch();
    const jpeg = await application.evaluate(({ nativeImage }) =>
      nativeImage
        .createFromBitmap(Buffer.alloc(800 * 600 * 4, 180), {
          width: 800,
          height: 600,
        })
        .toJPEG(80)
        .toString('base64'),
    );
    for (let n = 1; n <= 4; n++)
      await writeFile(
        path.join(source, `photo${n}.jpg`),
        Buffer.from(jpeg, 'base64'),
      );
    await application.evaluate(({ dialog }, source) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [source],
      });
    }, source);
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Overlay');
    await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
    await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
    await ready(page);
    const overlay = page.getByTestId('range-overlay');
    await page.getByLabel('Zakres na zdjęciu', { exact: true }).check();
    await overlay.waitFor();
    assert.equal(await overlay.locator('span').textContent(), 'Zakres: 1–9');
    assert.deepEqual(
      await overlay.evaluate((e) => [
        getComputedStyle(e).color,
        getComputedStyle(e).backgroundColor,
      ]),
      ['rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)'],
    );
    await drag(page, overlay.locator('span'), 90, 55);
    await page.waitForFunction(
      async () =>
        (await window.selector.snapshot()).value.view.rangeOverlay.x > 0.1,
    );
    await drag(
      page,
      page.getByRole('button', {
        name: 'Zmień rozmiar napisu zakresu',
        exact: true,
      }),
      50,
      20,
    );
    await page.waitForFunction(
      async () =>
        (await window.selector.snapshot()).value.view.rangeOverlay.fontSize >
        32,
    );
    const configured = await overlayState(page);
    await page.getByLabel('Zakres na zdjęciu', { exact: true }).uncheck();
    await overlay.waitFor({ state: 'detached' });
    await page.getByLabel('Zakres na zdjęciu', { exact: true }).check();
    assert.deepEqual(await overlayState(page), configured);
    await page
      .getByRole('button', { name: 'Pełny ekran (F11)', exact: true })
      .click();
    await page
      .getByRole('button', { name: 'Reset napisu', exact: true })
      .waitFor({ state: 'visible' });
    await overlay.waitFor({ state: 'visible' });
    await page
      .getByRole('button', { name: 'Wyjdź (F11)', exact: true })
      .click();
    await page.getByRole('button', { name: 'Pomiń', exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="range-overlay"] span')
          ?.textContent === 'Zakres: 10–18',
    );
    console.log(
      'PASS: transparent white range, dragging, corner resizing, toggle memory, fullscreen and live numbering.',
    );

    // A warm cache entry can have its decoded pixels discarded by Chromium.
    // Hold only its presentation decode; the retained JPEG must remain visible.
    await page.getByLabel('Zoom', { exact: true }).selectOption('300');
    await page.locator('.preview').evaluate((e) => {
      e.scrollLeft = 120;
      e.scrollTop = 100;
      e.dispatchEvent(new Event('scroll'));
    });
    await page.waitForFunction(
      async () => (await window.selector.snapshot()).value.view.scrollY === 100,
    );
    const snapshot = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    await page.evaluate((id) => {
      const decode = HTMLImageElement.prototype.decode;
      window.warmRelease = null;
      HTMLImageElement.prototype.decode = async function () {
        await decode.call(this);
        if (this.src.endsWith(id))
          await new Promise((resolve) => {
            window.warmRelease = resolve;
          });
      };
      window.emptyFrames = 0;
      window.badScrollFrames = 0;
      window.observeFrames = true;
      const sample = () => {
        if (!window.observeFrames) return;
        const image = document.querySelector('.preview-image-host img');
        const viewport = document.querySelector('.preview');
        if (!image?.complete || !image.naturalWidth) window.emptyFrames++;
        if (viewport.scrollLeft !== 120 || viewport.scrollTop !== 100)
          window.badScrollFrames++;
        requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    }, snapshot.source.images[1].id);
    const before = await page
      .locator('.preview-image-host img')
      .getAttribute('src');
    await page.locator('h1').click();
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => typeof window.warmRelease === 'function');
    assert.equal(
      await page.locator('.preview-image-host img').getAttribute('src'),
      before,
    );
    await page.evaluate(() => window.warmRelease());
    await ready(page);
    assert.notEqual(
      await page.locator('.preview-image-host img').getAttribute('src'),
      before,
    );
    assert.deepEqual(
      await page.evaluate(() => {
        window.observeFrames = false;
        return [window.emptyFrames, window.badScrollFrames];
      }),
      [0, 0],
    );
    console.log(
      'PASS: warm bitmap revalidation retains old image; zero empty DOM frames and no scroll jump at 300% zoom.',
    );

    await page
      .getByRole('button', { name: 'Zamknij projekt', exact: true })
      .click();
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .waitFor();
    await application.close();
    page = await launch();
    await continueFromHistory(page);
    await ready(page);
    assert.deepEqual(await overlayState(page), configured);
    assert.equal(
      await page.getByTestId('range-overlay').locator('span').textContent(),
      'Zakres: 10–18',
    );
    await page
      .getByRole('button', { name: 'Reset napisu', exact: true })
      .click();
    assert.deepEqual(await overlayState(page), {
      enabled: true,
      x: 0.05,
      y: 0.05,
      fontSize: 32,
    });
    console.log(
      'PASS: new Electron process restores saved overlay; reset restores defaults without hiding it.',
    );
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
