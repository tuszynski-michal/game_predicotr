import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { superGameSeriesAdminHref } from '../../../packages/board-search-ui/src/board-search-super-game.ts';
import { parseAdminNavigation } from '../src/features/catalog/admin-navigation-state.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const seriesId = '33333333-3333-4333-8333-333333333333';
const appsRoot = fileURLToPath(new URL('../../', import.meta.url));

test('a board marker link opens the series in the Supergry section', () => {
  const href = superGameSeriesAdminHref(gameId, seriesId);
  assert.equal(
    href,
    `?workspace=games&game=${gameId}&section=super-games&series=${seriesId}`,
  );
  // The Admin's own navigation parser must read the link back (TASK-0934).
  assert.deepEqual(parseAdminNavigation(href), {
    gameId,
    section: 'super-games',
    seriesId,
    workspace: 'games',
  });
});

function sources(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) {
      return name === 'node_modules' || name === '.next' ? [] : sources(path);
    }
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

test('only the Admin board search declares the series link capability', () => {
  const declaring = [
    ...sources(join(appsRoot, 'admin', 'src')),
    ...sources(join(appsRoot, 'reviewer', 'src')),
  ].filter((path) =>
    readFileSync(path, 'utf8').includes('superGameSeriesHref:'),
  );
  assert.deepEqual(
    declaring.map((path) => relative(appsRoot, path).split(sep).join('/')),
    ['admin/src/features/board-search/board-search-workspace.tsx'],
  );
});
