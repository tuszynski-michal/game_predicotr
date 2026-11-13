import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import {
  COHORT_PAGE_LIMIT,
  RECORDING_PAGE_LIMIT,
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
  assert.equal(
    reasonLabel('VALIDATION_REGRESSED:boards_within_cells'),
    'Pogorszenie na VALIDATION: plansze bez cięcia symboli (pola w 10%)',
  );
  assert.equal(
    reasonLabel('SOMETHING_NEW'),
    'Nieopisany powód blokady (SOMETHING_NEW)',
  );
  assert.equal(reasonLabel(null), '');
  assert.equal(
    reasonList(['GRID_RUN_COHORT_EMPTY', 'X']),
    'Kohorta nie ma danych TRAIN; Nieopisany powód blokady (X)',
  );
});

test('scope changes and pending learning transitions explain the next safe action', () => {
  assert.match(
    reasonLabel('GRID_MODEL_EVALUATION_SCOPE_STALE'),
    /Wersja domyślna zmieniła się.*nowej bazy.*nowy przebieg/,
  );
  assert.match(
    reasonLabel('GRID_LEARNING_BUSY'),
    /Trwa zapis.*Odczekaj chwilę i ponów/,
  );
  assert.match(
    reasonLabel('GRID_LEARNING_CANCELLATION_PENDING'),
    /Anulowanie trwa.*Poczekaj.*zanim wznowisz/,
  );
  for (const code of [
    'GRID_MODEL_EVALUATION_SCOPE_STALE',
    'GRID_LEARNING_BUSY',
    'GRID_LEARNING_CANCELLATION_PENDING',
  ])
    assert.doesNotMatch(reasonLabel(code), /Nieopisany powód/);
});

test('every grid-learning blocker raised by the API has a Polish label (TASK-1204)', () => {
  const root = new URL('../../../services/', import.meta.url);
  const files = [
    'api/src/game_predictor_api/application/grid_correction_learning.py',
    'api/src/game_predictor_api/storage/grid_correction_split.py',
    'api/src/game_predictor_api/domain/grid_correction_split.py',
    'api/src/game_predictor_api/domain/grid_correction_incremental_split.py',
    'worker/src/game_predictor_worker/training_core/grid_training_admission.py',
  ];
  const codes = new Set();
  for (const file of files)
    for (const match of readFileSync(new URL(file, root), 'utf8').matchAll(
      /"((?:GRID|CONTENT)_[A-Z_]+)"/g,
    ))
      codes.add(match[1]);
  assert.ok(codes.has('GRID_CORRECTION_POPULATION_LIMIT'));
  const unlabeled = [...codes].filter((code) =>
    /Nieopisany powód/.test(reasonLabel(code)),
  );
  assert.deepEqual(unlabeled, []);
  assert.match(
    reasonLabel('GRID_CORRECTION_POPULATION_LIMIT'),
    /limit uczenia \(20 000\)/,
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

test('page sizes never exceed what the list endpoints accept', () => {
  const openapi = JSON.parse(
    readFileSync(
      new URL(
        '../../../packages/admin-api-client/openapi/openapi.json',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  const maximum = (operationId) => {
    for (const methods of Object.values(openapi.paths))
      for (const operation of Object.values(methods))
        if (operation.operationId === operationId) {
          const limit = operation.parameters.find(
            (item) => item.name === 'limit',
          );
          return limit.schema.maximum;
        }
    throw new Error(operationId);
  };
  assert.ok(COHORT_PAGE_LIMIT <= maximum('listGridTrainingCohorts'));
  assert.ok(RECORDING_PAGE_LIMIT <= maximum('listSourceRecordingGroups'));
});
