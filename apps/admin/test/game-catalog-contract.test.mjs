import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/games/game-catalog.tsx', import.meta.url),
  'utf8',
);
const stateSource = await readFile(
  new URL('../src/features/games/game-catalog-state.ts', import.meta.url),
  'utf8',
);

test('game catalog exposes status filters and an explicit restore action', () => {
  assert.match(source, /game-filter-\$\{status\}/);
  assert.match(source, /Przywróć jako szkic/);
  assert.match(source, /GamesFilteredEmpty/);
});

test('game catalog does not expose physical deletion', () => {
  assert.doesNotMatch(source, />\s*Usuń\s*</);
  assert.doesNotMatch(source, /deleteGame/);
});

test('the complete selectable game card activates its game context', () => {
  assert.match(source, /data-selectable=\{selectable\}/);
  assert.match(source, /onClick=\{handleRowClick\}/);
  assert.match(
    source,
    /target\.closest\('button, input, select, textarea, a'\)/,
  );
});

test('game card keeps the stable code compact and separates the layout goal', () => {
  assert.match(source, /className="gameStableCode"/);
  assert.match(source, /className="gameLayoutGoal"/);
});

test('game card exposes storage maintenance and disables mutations', () => {
  assert.match(source, /Magazyn: \{game\.storageVersion\}/);
  assert.match(source, /tryb tylko do odczytu/);
  assert.match(source, /disabled=\{!game\.storageWriteAvailable\}/);
  assert.match(
    source,
    /disabled=\{restorePending \|\| !game\.storageWriteAvailable\}/,
  );
});

test('game editor records the page format and card exposes its shared-geometry readiness', () => {
  assert.match(source, /name="shapeGeometryConfiguration"/);
  assert.match(stateSource, /Pełna strona z ramką/);
  assert.match(source, /Pierwszy import nadal wymaga/);
  assert.match(source, /className="gameGeometryState"/);
  assert.match(source, /profil wspólny #/);
});

test('page format shows the grid engine profile, its model state and the 777 note', () => {
  assert.match(stateSource, /grid_profile_777_v2: '777 v2'/);
  assert.match(stateSource, /grid_profile_mumie_v1: 'Mumie'/);
  assert.match(source, /<GridEngineProfileHint/);
  assert.match(source, /Profil 777 v2 służy również przyszłym wersjom gry 777/);
  assert.match(source, /loadGridEngineProfiles\(api\)/);
  assert.match(source, /className="gamePageFormat"/);
  assert.match(source, /Format strony:/);
});

test('TASK-0931: create and edit forms select the super game kind from the API registry', () => {
  assert.match(source, /<span>Supergra<\/span>/);
  assert.match(source, /name="superGameKind"/);
  assert.match(
    source,
    /superGameKindOptions\(superGameKinds, draft\.superGameKind\)/,
  );
  assert.match(source, /loadSuperGameKinds\(api\)/);
  assert.match(source, /superGameKind: game\.superGameKind/);
  assert.match(source, /className="gameSuperGameKind"/);
  assert.match(stateSource, /superGameKind: 'none'/);
});
