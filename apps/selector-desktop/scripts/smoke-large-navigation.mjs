import { _electron as electron } from 'playwright-core';
import electronExecutable from 'electron';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createOwnedSmoke, boundedSmokeStep } from './release-support.mjs';
const source = process.env.SELECTOR_MEASUREMENT_SOURCE;
assert.ok(source, 'Explicit read-only source required');
await mkdir('.tmp', { recursive: true });
const fixture = await mkdtemp(path.resolve('.tmp/large-navigation-'));
const userData = path.join(fixture, 'user');
const smoke = createOwnedSmoke({
  name: 'large-navigation',
  fixture,
  tempRoot: path.resolve('.tmp'),
  userData: [userData],
});
const local = process.argv.includes('--local');
const report = {
  machine: {
    platform: os.platform(),
    release: os.release(),
    cpu: os.cpus()[0]?.model,
    memoryBytes: os.totalmem(),
  },
  imageSamples: [],
  samples: [],
  memory: [],
  limitations: [
    'Existing source read only; isolated new project without existing decisions.',
    'Rendering opportunity measured with animation frames, not monitor photons.',
  ],
};
let application;
function summary(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    count: sorted.length,
    p95: sorted[Math.ceil(sorted.length * 0.95) - 1],
    maximum: sorted.at(-1),
  };
}
try {
  await boundedSmokeStep(async () => {
    application = await smoke.launch(electron, {
      executablePath: local
        ? electronExecutable
        : path.resolve(process.argv[2]),
      args: [...(local ? ['.'] : []), `--user-data-dir=${userData}`],
      timeout: 20000,
    });
    let page = await application.firstWindow();
    page.setDefaultTimeout(15000);
    await application.evaluate(
      ({ dialog }, paths) => {
        const queue = [...paths];
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [queue.shift()],
        });
        dialog.showMessageBox = async () => ({ response: 1 });
      },
      [source, path.join(fixture, 'project'), path.join(fixture, 'output')],
    );
    const created = await page.evaluate(() =>
      window.selector.create({
        gameName: 'Large measurement',
        gameUpdate: 'a1',
        firstLayout: 1,
        direction: 'ascending',
        sequenceUpperBound: 500000,
        customLocations: true,
        localStorageConfirmed: true,
      }),
    );
    assert.equal(created.ok, true, JSON.stringify(created.error));
    report.fileCount = created.value.source.images.length;
    const projectId = created.value.projectId;
    const images = created.value.source.images;
    report.version = await application.evaluate(({ app }) => app.getVersion());
    // Test-only adapter installs the real native snapshot without rescanning the source.
    await application.evaluate(({ ipcMain }) => {
      const snapshot = ipcMain._invokeHandlers.get('selector:snapshot');
      ipcMain.removeHandler('selector:begin');
      ipcMain.handle('selector:begin', async (event) => {
        const result = await snapshot(event);
        if (!result.ok) return result;
        return {
          ok: true,
          value: { kind: 'existing', workspace: result.value },
        };
      });
    });
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    console.log(`Created isolated project: ${report.fileCount} source files.`);
    async function settled() {
      await page.waitForFunction(() => {
        const img = document.querySelector('.preview img');
        return (
          img?.complete &&
          img.naturalWidth > 0 &&
          !document.querySelector('.preview [role=status]') &&
          [...document.querySelectorAll('button')].some(
            (b) => b.textContent === 'Zakres' && !b.disabled,
          )
        );
      });
    }
    await settled();
    async function measure(key, target) {
      await page.evaluate((target) => {
        window.paintElapsed = null;
        document.addEventListener(
          'keydown',
          () => {
            const started = performance.now();
            let blank = 0;
            const frame = () => {
              const image = document.querySelector('.preview img');
              if (!image || !image.getBoundingClientRect().width) blank++;
              if (image?.src === target) {
                requestAnimationFrame(() => {
                  window.paintElapsed = performance.now() - started;
                  window.blankFrames = blank;
                });
              } else requestAnimationFrame(frame);
            };
            requestAnimationFrame(frame);
          },
          { once: true, capture: true },
        );
      }, target);
      await page.keyboard.press(key);
      await page.waitForFunction(() => window.paintElapsed !== null);
      const result = await page.evaluate(() => ({
        ms: window.paintElapsed,
        blankFrames: window.blankFrames,
      }));
      await settled();
      return result;
    }
    report.memory.push(
      await application.evaluate(({ app }) =>
        app.getAppMetrics().map((p) => ({ type: p.type, ...p.memory })),
      ),
    );
    for (const [region, base] of [
      ['start', 0],
      ['middle', Math.floor(images.length / 2)],
      ['end', images.length - 10],
    ]) {
      await page.evaluate(
        async ({ projectId, base }) => {
          const w = await window.selector.snapshot();
          const result = await window.selector.execute({
            projectId,
            operationId: crypto.randomUUID(),
            command: {
              kind: 'navigate',
              imageId: w.value.source.images[base].id,
            },
          });
          if (!result.ok) throw Error(JSON.stringify(result));
        },
        { projectId, base },
      );
      await page
        .getByRole('button', { name: 'Wybierz kolejny folder', exact: true })
        .click();
      await settled();
      // Source IDs change after reopening; use the current bootstrap URLs.
      const current = (await page.evaluate(() => window.selector.snapshot()))
        .value;
      report.imageSamples.push(
        await page.evaluate(() => {
          const img = document.querySelector('.preview img');
          return { width: img.naturalWidth, height: img.naturalHeight };
        }),
      );
      console.log(`Measuring ${region}`);
      for (const step of [1, 2, 3, 4, 20]) {
        // End region uses negative direction when a full step cannot fit.
        const sign = base + step < images.length ? 1 : -1;
        const target = base + step * sign;
        await page
          .getByLabel('Skok', { exact: true })
          .selectOption(String(step));
        await page.locator('h1').click();
        await settled();
        const first = await measure(
          sign > 0 ? 'ArrowRight' : 'ArrowLeft',
          current.source.images[target].url,
        );
        report.samples.push({ region, step, kind: 'first', ...first });
        await measure(
          sign > 0 ? 'ArrowLeft' : 'ArrowRight',
          current.source.images[base].url,
        );
        for (let n = 0; n < 10; n++) {
          const forward = n % 2 === 0;
          report.samples.push({
            region,
            step,
            kind: 'warm',
            ...(await measure(
              (forward ? sign : -sign) > 0 ? 'ArrowRight' : 'ArrowLeft',
              current.source.images[forward ? target : base].url,
            )),
          });
        }
      }
      report.memory.push(
        await application.evaluate(({ app }) =>
          app.getAppMetrics().map((p) => ({ type: p.type, ...p.memory })),
        ),
      );
    }
    report.warm = summary(
      report.samples.filter((s) => s.kind === 'warm').map((s) => s.ms),
    );
    report.blankFrames = report.samples.reduce(
      (sum, s) => sum + s.blankFrames,
      0,
    );
    if (!process.argv.includes('--baseline'))
      assert.equal(report.blankFrames, 0, 'No empty transition frames');
    assert.ok(report.warm.p95 <= 50, JSON.stringify(report.warm));
    await page
      .getByRole('button', { name: 'Zamknij projekt', exact: true })
      .click();
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .waitFor();
    await application.close();
  }, 220000);
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
  report.failure = String(error);
} finally {
  await mkdir('../../artifacts/selector-smooth-20261103', { recursive: true });
  await writeFile(
    process.env.SELECTOR_LARGE_REPORT ??
      '../../artifacts/selector-smooth-20261103/large-navigation.json',
    JSON.stringify(report, null, 2),
  );
  console.log(
    JSON.stringify({
      fileCount: report.fileCount,
      warm: report.warm,
      blankFrames: report.blankFrames,
      failure: report.failure,
    }),
  );
  await smoke.finish();
}
