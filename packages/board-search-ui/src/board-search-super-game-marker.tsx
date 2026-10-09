'use client';

import type { SuperGameStateResponse } from '@game-predictor/admin-api-client';

import {
  SUPER_GAME_STALE_BANNER,
  SUPER_GAME_STALE_HINT,
  type BoardSearchSuperGameMarker,
  superGameMarkerLabel,
  superGameMarkerLink,
  superGameMarkerNotes,
  superGameSpinLabel,
  superGameStateIsStale,
} from './board-search-super-game';

/**
 * The gold super game marker of a result card or an approximate-win row
 * (TASK-0935). The link to the Admin's series view appears only when the
 * data source declares `superGameSeriesHref` (the Admin); the online share
 * and the management panel show the label alone.
 */
export function SuperGameMarkerBadge({
  gameId,
  marker,
  seriesHref,
}: {
  readonly gameId: string;
  readonly marker: BoardSearchSuperGameMarker;
  readonly seriesHref?: (gameId: string, seriesId: string) => string;
}) {
  const label = superGameMarkerLabel(marker);
  const link = superGameMarkerLink(marker, gameId, seriesHref);
  // A series without a super symbol hides its spin in the label.
  const spin =
    marker.kind === 'in_series' && marker.superSymbolCode == null
      ? superGameSpinLabel(marker)
      : '';
  const notes = superGameMarkerNotes(marker);
  return (
    <span className="boardSearchSuperGame">
      <strong className="boardSearchSuperGameLabel">{label}</strong>
      {spin === '' ? null : (
        <span className="boardSearchSuperGameSpin">({spin})</span>
      )}
      {notes.map((note) => (
        <small className="boardSearchSuperGameNote" key={note}>
          {note}
        </small>
      ))}
      {link === null ? null : (
        <a
          className="boardSearchSuperGameLink"
          href={link.href}
          rel="noreferrer"
          target="_blank"
        >
          {link.label}
        </a>
      )}
    </span>
  );
}

/** „Serie w trakcie przeliczania” for the whole result while `fresh = false`. */
export function SuperGameStateBanner({
  state,
}: {
  readonly state: SuperGameStateResponse | null | undefined;
}) {
  if (!superGameStateIsStale(state)) {
    return null;
  }
  return (
    <p className="feedbackBanner boardSearchSuperGameStale" role="status">
      <strong>{SUPER_GAME_STALE_BANNER}</strong> {SUPER_GAME_STALE_HINT}
    </p>
  );
}
