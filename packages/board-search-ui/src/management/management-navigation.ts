import type { ManagementSnapshotResponse } from '@game-predictor/admin-api-client';

export interface ManagementLocation {
  pointId: string | null;
  machineId: string | null;
  gameId: string | null;
  stake: number | null;
}

const EMPTY: ManagementLocation = {
  pointId: null,
  machineId: null,
  gameId: null,
  stake: null,
};
const STAKES = new Set([2000, 1000, 600, 400, 200, 120]);
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function managementLocationFromUrl(search: string): ManagementLocation {
  const params = new URLSearchParams(search);
  const id = (key: string) => {
    const value = params.get(key);
    return value && UUID.test(value) ? value : null;
  };
  const stake = Number(params.get('mpStake'));
  return {
    pointId: id('mpPoint'),
    machineId: id('mpMachine'),
    gameId: id('mpGame'),
    stake: params.has('mpStake') && STAKES.has(stake) ? stake : null,
  };
}

export function validManagementLocation(
  wanted: ManagementLocation,
  snapshot: ManagementSnapshotResponse,
): ManagementLocation {
  const point = snapshot.points.find((item) => item.id === wanted.pointId);
  if (!point) return EMPTY;
  const machine = point.machines.find((item) => item.id === wanted.machineId);
  if (!machine) return { ...EMPTY, pointId: point.id };
  const assignment = machine.assignments.find(
    (item) => item.gameId === wanted.gameId,
  );
  return {
    pointId: point.id,
    machineId: machine.id,
    gameId: assignment ? assignment.gameId : null,
    stake: assignment ? wanted.stake : null,
  };
}

export function managementUrlWithLocation(
  href: string,
  location: ManagementLocation,
): string {
  const url = new URL(href);
  for (const [key, value] of [
    ['mpPoint', location.pointId],
    ['mpMachine', location.machineId],
    ['mpGame', location.gameId],
    ['mpStake', location.stake],
  ] as const) {
    if (value === null) url.searchParams.delete(key);
    else url.searchParams.set(key, String(value));
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function sameManagementLocation(
  a: ManagementLocation,
  b: ManagementLocation,
): boolean {
  return (
    a.pointId === b.pointId &&
    a.machineId === b.machineId &&
    a.gameId === b.gameId &&
    a.stake === b.stake
  );
}
