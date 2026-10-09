import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  managementLocationFromUrl,
  managementUrlWithLocation,
  validManagementLocation,
} from '../src/management/management-navigation.ts';

const pointId = '11111111-1111-4111-8111-111111111111';
const machineId = '22222222-2222-4222-8222-222222222222';
const gameId = '33333333-3333-4333-8333-333333333333';
const snapshot = {
  activeGames: [],
  points: [
    { id: pointId, machines: [{ id: machineId, assignments: [{ gameId }] }] },
  ],
};

test('management URL keeps unrelated parameters and stake is selection only', () => {
  const wanted = { pointId, machineId, gameId, stake: 120 };
  const href = managementUrlWithLocation(
    'https://example.test/admin?workspace=management&filter=x#top',
    wanted,
  );
  assert.equal(
    href,
    `/admin?workspace=management&filter=x&mpPoint=${pointId}&mpMachine=${machineId}&mpGame=${gameId}&mpStake=120#top`,
  );
  assert.deepEqual(
    managementLocationFromUrl(new URL(href, 'https://example.test').search),
    wanted,
  );
});

test('invalid and removed scope falls back to nearest valid ancestor', () => {
  const wanted = managementLocationFromUrl(
    `?mpPoint=${pointId}&mpMachine=${machineId}&mpGame=${gameId}&mpStake=2000`,
  );
  assert.deepEqual(validManagementLocation(wanted, snapshot), wanted);
  assert.deepEqual(
    validManagementLocation(
      { ...wanted, gameId: '44444444-4444-4444-8444-444444444444' },
      snapshot,
    ),
    { pointId, machineId, gameId: null, stake: null },
  );
  assert.deepEqual(
    validManagementLocation(
      { ...wanted, machineId: '44444444-4444-4444-8444-444444444444' },
      snapshot,
    ),
    { pointId, machineId: null, gameId: null, stake: null },
  );
  assert.equal(
    managementLocationFromUrl('?mpPoint=bad&mpStake=42').pointId,
    null,
  );
});
