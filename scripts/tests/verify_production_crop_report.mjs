import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM, VirtualConsole } from 'jsdom';

const errors = [];
const console = new VirtualConsole();
console.on('jsdomError', (error) => errors.push(error));
const dom = new JSDOM(readFileSync(process.argv[2], 'utf8'), {
  runScripts: 'dangerously',
  virtualConsole: console,
});
try {
  const document = dom.window.document;
  assert.match(document.querySelector('h1').textContent, /margines/);
  assert.equal(document.querySelectorAll('.pairs .cell').length, 15);
  assert.ok(document.querySelectorAll('#board option').length > 0);
  document.getElementById('model').click();
  assert.equal(
    document.getElementById('model').getAttribute('aria-pressed'),
    'true',
  );
  assert.match(
    document.getElementById('overview').textContent,
    /Rzeczywiste wyjście/,
  );
  if (process.argv.includes('--expect-no-model-nodes')) {
    assert.match(
      document.getElementById('overview').textContent,
      /Brak jednoznacznej siatki modelu/,
    );
    assert.equal(document.querySelectorAll('.model-line').length, 0);
  }
  if (process.argv.includes('--expect-incorrect-geometry')) {
    assert.match(
      document.getElementById('geometry-status').textContent,
      /Dopasowana, lecz błędna geometria/,
    );
    assert.match(
      document.getElementById('geometry-status').textContent,
      /Zgodność z zapisaną geometrią — nie niezależna ocena jakości/,
    );
    if (process.argv.includes('--expect-full-geometry')) {
      assert.match(
        document.getElementById('geometry-status').textContent,
        /Całe zdjęcie: niezgodne\. Fałszywe detekcje: 1; nadmiarowe detekcje \(duplikaty\): 0/,
      );
    } else {
      assert.match(
        document.getElementById('geometry-status').textContent,
        /Całe zdjęcie: brak oceny\. Fałszywe detekcje: brak oceny; nadmiarowe detekcje \(duplikaty\): brak oceny/,
      );
      assert.match(
        document.getElementById('overview').textContent,
        /pozycja 8/,
      );
    }
  }
  const points = [...document.querySelectorAll('#visual polyline')].map((e) =>
    e.getAttribute('points'),
  );
  document.getElementById('grid').click();
  assert.equal(document.querySelectorAll('#visual polyline').length, 0);
  document.getElementById('grid').click();
  assert.deepEqual(
    [...document.querySelectorAll('#visual polyline')].map((e) =>
      e.getAttribute('points'),
    ),
    points,
  );
  document.getElementById('human').click();
  assert.equal(
    document.getElementById('human').getAttribute('aria-pressed'),
    'true',
  );
  if (process.argv.includes('--expect-approved')) {
    assert.ok(document.querySelectorAll('#visual .outline').length > 0);
    assert.match(
      document.getElementById('pairs').textContent,
      /Klasa człowieka: J/,
    );
    const cells = document.querySelectorAll('.pairs .cell');
    assert.match(
      cells[0].querySelector('.pair').textContent,
      /Grafika zachowana/,
    );
    assert.match(
      cells[0].querySelector('.pair').textContent,
      /Grafika przycięta · obce pole · niejednoznaczność · obcy pełny symbol/,
    );
    assert.match(
      cells[1].textContent,
      /Zasłonięta — pełności grafiki nie oceniamy/,
    );
    assert.match(
      cells[2].textContent,
      /Poza kadrem — pełności grafiki nie oceniamy/,
    );
    assert.match(
      cells[1].textContent,
      /Klasa człowieka: 10; brak dostępnego wyniku klasyfikatora/,
    );
    for (const state of ['occluded', 'out_of_frame', 'unknown']) {
      const outline = document.querySelector(`.outline[data-state="${state}"]`);
      assert.ok(outline);
      assert.equal(
        dom.window
          .getComputedStyle(outline)
          .getPropertyValue('stroke-dasharray'),
        '7 4',
      );
    }
    assert.match(
      document.querySelector('.legend').textContent,
      /Przerywane obrysy grafik/,
    );
    document.getElementById('content').click();
    assert.equal(document.querySelectorAll('#visual .outline').length, 0);
    document.getElementById('content').click();
    assert.ok(document.querySelectorAll('#visual .outline').length > 0);
  }
  const select = document.getElementById('board');
  if (select.options.length > 1) {
    select.value = String(select.options.length - 1);
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    assert.equal(document.getElementById('next').disabled, true);
    document.getElementById('prev').click();
    assert.equal(document.getElementById('next').disabled, false);
  }
  assert.equal(
    document.querySelectorAll('img[src=""],img:not([src])').length,
    0,
  );
  assert.doesNotMatch(
    document.getElementById('inputs').textContent,
    /źródłowy(?:null|undefined)/,
  );
  assert.equal(errors.length, 0, errors.map(String).join('\n'));
} finally {
  dom.window.close();
}
process.stdout.write('CROP_HTML_DOM_PASS\n');
