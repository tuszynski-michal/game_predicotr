import type {
  SuperGameMarkerResponse,
  SuperGameStateResponse,
} from '@game-predictor/admin-api-client';

/**
 * Super game markers of board search and approximate win (TASK-0935, D-535).
 * A marker is the board's role in the *published* series generation; a board
 * without one is in base mode according to that generation. Whether the
 * generation is current is the response-level `superGameState`.
 */

/** The marker as every consumer gets it; the Admin's also carries `seriesId`. */
export type BoardSearchSuperGameMarker = SuperGameMarkerResponse;

export const SUPER_GAME_STALE_BANNER = 'Serie w trakcie przeliczania';
export const SUPER_GAME_STALE_HINT =
  'Oznaczenia supergry mogą być nieaktualne, także przy planszach bez oznaczenia.';
export const SUPER_GAME_DEFINE_LINK = 'Zdefiniuj super symbol';
export const SUPER_GAME_OPEN_LINK = 'Pokaż serię';

/**
 * „Supergra: trigger”, „Supergra: spin 3/10, symbol K” or, while the series
 * has no super symbol, „Supergra: super symbol do zdefiniowania”.
 */
export function superGameMarkerLabel(
  marker: Pick<
    BoardSearchSuperGameMarker,
    'kind' | 'seriesLength' | 'spinIndex' | 'superSymbolCode'
  >,
): string {
  if (marker.kind === 'trigger') {
    return 'Supergra: trigger';
  }
  if (marker.superSymbolCode === null || marker.superSymbolCode === undefined) {
    return 'Supergra: super symbol do zdefiniowania';
  }
  return `Supergra: ${superGameSpinLabel(marker)}, symbol ${marker.superSymbolCode}`;
}

/** „spin 3/10”; empty for the trigger board. */
export function superGameSpinLabel(
  marker: Pick<BoardSearchSuperGameMarker, 'seriesLength' | 'spinIndex'>,
): string {
  return marker.spinIndex === null || marker.spinIndex === undefined
    ? ''
    : `spin ${marker.spinIndex}/${marker.seriesLength}`;
}

/**
 * What else the operator should know about the series behind a marker: the
 * label alone would otherwise hide that its length or its trigger is uncertain.
 */
export function superGameMarkerNotes(
  marker: Pick<BoardSearchSuperGameMarker, 'completeness' | 'runVerification'>,
): readonly string[] {
  const notes: string[] = [];
  if (marker.completeness === 'incomplete') {
    notes.push('Seria niepełna: brakuje plansz do końca serii.');
  }
  if (marker.runVerification === 'unverified') {
    notes.push('Trigger lub retrigger oparty na predykcji modelu.');
  }
  return notes;
}

/** Only an explicit `fresh = false` warns; an absent state (old receipt) does not. */
export function superGameStateIsStale(
  state: Pick<SuperGameStateResponse, 'fresh'> | null | undefined,
): boolean {
  return state !== null && state !== undefined && !state.fresh;
}

/**
 * Admin URL of the series view (TASK-0934): relative to the Admin page, so the
 * link works on whatever origin the Admin is served from.
 */
export function superGameSeriesAdminHref(
  gameId: string,
  seriesId: string,
): string {
  const parameters = new URLSearchParams({
    workspace: 'games',
    game: gameId,
    section: 'super-games',
    series: seriesId,
  });
  return `?${parameters.toString()}`;
}

/**
 * The link of a marker: only when the data source can link to the Admin
 * (`superGameSeriesHref`, Admin only) and the marker carries its series.
 */
export function superGameMarkerLink(
  marker: Pick<BoardSearchSuperGameMarker, 'seriesId' | 'superSymbolCode'>,
  gameId: string,
  seriesHref: ((gameId: string, seriesId: string) => string) | undefined,
): { readonly href: string; readonly label: string } | null {
  if (
    seriesHref === undefined ||
    marker.seriesId === null ||
    marker.seriesId === undefined
  ) {
    return null;
  }
  return {
    href: seriesHref(gameId, marker.seriesId),
    label:
      marker.superSymbolCode === null || marker.superSymbolCode === undefined
        ? SUPER_GAME_DEFINE_LINK
        : SUPER_GAME_OPEN_LINK,
  };
}
