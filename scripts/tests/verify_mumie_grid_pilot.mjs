import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const template = readFileSync(
  new URL('../templates/mumie-grid-pilot.html', import.meta.url),
  'utf8',
);
const detected = { state: 'detected', cells: Array(15).fill(true) };
const missing = { state: 'missing', cells: [] };
const study = {
  id: 'opaque-study',
  cards: [
    { id: 'first', position: 0, A: detected, B: missing },
    { id: 'second', position: 1, A: detected, B: detected },
  ],
};
let download;
let filename;
const dom = new JSDOM(template.replace('__CARDS__', JSON.stringify(study)), {
  runScripts: 'dangerously',
  url: 'https://pilot.invalid/',
  beforeParse(window) {
    window.URL.createObjectURL = (blob) => {
      download = blob;
      return 'blob:pilot';
    };
    window.URL.revokeObjectURL = () => {};
    window.HTMLAnchorElement.prototype.click = function () {
      filename = this.download;
    };
  },
});
const { document } = dom.window;
assert.equal(document.querySelectorAll('select').length, 30);
assert.equal(document.querySelectorAll('select:disabled').length, 15);
const field = document.querySelector('select');
field.value = 'cut';
field.dispatchEvent(new dom.window.Event('change'));
document.querySelector('section button').click();
assert.match(document.querySelector('#progress').textContent, /1 \/ 2/);
document.querySelector('#next').click();
for (const button of document.querySelectorAll('section button'))
  button.click();
document.querySelector('#prev').click();
assert.equal(document.querySelector('select').value, 'cut');
assert.match(document.querySelector('#progress').textContent, /2 \/ 2/);
document.querySelector('#save').click();
assert.equal(filename, 'oceny.json');
const reader = new dom.window.FileReader();
const loaded = new Promise((resolve) => {
  reader.onload = () => resolve(reader.result);
});
reader.readAsText(download);
const output = JSON.parse(await loaded);
assert.equal(output.study, study.id);
assert.deepEqual(output.votes.first.A, ['cut', ...Array(14).fill('full')]);
assert.deepEqual(output.votes.first.B, Array(15).fill('missing'));
dom.window.close();
console.log(
  'Ślepa ocena, nawigacja, brak planszy i pobranie głosów z HTML: PASS.',
);
