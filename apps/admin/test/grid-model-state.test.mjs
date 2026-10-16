import assert from 'node:assert/strict';
import test from 'node:test';
import {
  clearModelCommand,
  cohortLabel,
  modelCommandKey,
  publishBlocker,
  readModelCommand,
  reasonLabel,
  reasonList,
  saveModelCommand,
  versionLabel,
  versionName,
} from '../src/features/model-quality/grid-model-state.ts';

test('codes are readable, evaluation reasons are explained and unknown codes stay visible', () => {
  assert.equal(
    reasonLabel('GRID_MODEL_EVALUATION_STALE'),
    'Dowód oceny jest nieaktualny — sprawdź aktualność',
  );
  assert.equal(
    reasonLabel('REGRESSION_REGRESSED:duplicate_predictions'),
    'Pogorszenie na REGRESSION: zdublowane detekcje',
  );
  assert.equal(
    reasonLabel('VALIDATION_NOT_IMPROVED:boards_correct'),
    'Brak poprawy gry treningowej: plansze poprawne',
  );
  assert.equal(reasonLabel('SOMETHING_NEW'), 'Inny powód (SOMETHING_NEW)');
  assert.equal(reasonLabel(null), '');
  assert.equal(
    reasonList(['GRID_RUN_COHORT_EMPTY', 'X']),
    'Kohorta nie ma danych TRAIN; Inny powód (X)',
  );
});

const manifest = (id, family, version) => ({
  versionId: id,
  familyLabel: family,
  version,
});

test('versions, bases and cohorts are named without identifiers', () => {
  const versions = [
    { manifest: manifest('a', 'Mumie', 'v1') },
    { manifest: manifest('b', '777 v2', 'v1') },
  ];
  assert.equal(versionLabel(versions[1].manifest), '777 v2 · v1');
  assert.equal(versionName(versions, 'a'), 'Mumie · v1');
  assert.equal(versionName(versions, 'zzz'), 'wersja spoza katalogu');
  const label = cohortLabel({
    id: 'c',
    createdAt: '2026-10-16T10:00:00Z',
    mode: 'grid-only',
    status: 'frozen',
  });
  assert.match(label, /^Kohorta z .+ · tylko siatki · zamrożona$/);
  assert.doesNotMatch(label, /\bc\b · /);
});

const view = (verdict, states = ['current']) => ({
  report: verdict === null ? null : { verdict },
  currentness: states.map((state) => ({ state })),
});

test('publication is offered only for a measured PASS with current proofs', () => {
  assert.equal(publishBlocker(null), 'Wybierz ocenę kandydata');
  assert.equal(publishBlocker(view(null)), 'Ocena nie ma jeszcze raportu');
  assert.match(publishBlocker(view('REVISE')), /wymaga poprawy/);
  assert.match(publishBlocker(view('NOT_EVALUABLE')), /Nie można ocenić/);
  assert.match(
    publishBlocker(view('PASS', ['current', 'stale'])),
    /nieaktualny/,
  );
  assert.match(publishBlocker(view('PASS', ['unavailable'])), /nieaktualny/);
  assert.equal(publishBlocker(view('PASS', ['current', 'current'])), null);
});

test('a saved command survives until its own confirmation', () => {
  const items = new Map();
  const storage = {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
    removeItem: (key) => items.delete(key),
  };
  const key = modelCommandKey('http://api', 'game-a', 'run');
  assert.notEqual(key, modelCommandKey('http://api', 'game-b', 'run'));
  const command = {
    kind: 'run',
    target: 'c',
    body: { idempotencyKey: 'k1', cohortId: 'c' },
  };
  saveModelCommand(storage, key, command);
  assert.deepEqual(readModelCommand(storage, key), command);
  clearModelCommand(storage, key, 'other-key');
  assert.deepEqual(readModelCommand(storage, key), command);
  clearModelCommand(storage, key, 'k1');
  assert.equal(readModelCommand(storage, key), null);
  items.set(key, '{"kind":1}');
  assert.throws(() => readModelCommand(storage, key), /nieczytelne/);
});
