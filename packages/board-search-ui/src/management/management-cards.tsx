'use client';

/* Symbol assets are protected API responses. */
/* eslint-disable @next/next/no-img-element */

import type {
  ManagementStake,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { formatZloty } from '../index';
import type { ManagementGameClient } from './management-client';
import type { ManagementCardState } from './management-slot-state';

export function managementAmount(
  credits: number,
  stake: number,
  spinCost: number,
): string {
  return formatZloty(
    spinCost > 0
      ? Math.sign(credits) * Math.round((Math.abs(credits) * stake) / spinCost)
      : credits * 10,
  );
}
export function managementDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('pl-PL') : '—';
}

/** Immutable start codes with catalog thumbnails; never fetches current boards. */
export function ManagementBoardPreview({
  codes,
  symbols = [],
  api,
  gameId,
}: {
  codes: readonly (string | null)[] | null | undefined;
  symbols?: readonly SymbolResponse[];
  api?: Pick<ManagementGameClient, 'symbolImageAssetUrl'>;
  gameId?: string;
}) {
  return (
    <div
      className="management-board-preview"
      aria-label="Symbole zapisanej planszy"
    >
      {Array.from({ length: 15 }, (_, index) => (
        <span key={index}>
          {(() => {
            const code = codes?.[index];
            const symbol = symbols.find((item) => item.code === code);
            return symbol?.imagePath && api && gameId ? (
              <img
                alt={code ?? '?'}
                src={api.symbolImageAssetUrl(gameId, symbol.id)}
              />
            ) : (
              (code ?? '?')
            );
          })()}
        </span>
      ))}
    </div>
  );
}

/** A whole stake is one keyboard-accessible choice, without miniature charts. */
export function ManagementCards({
  cards,
  writeAllowed,
  busy,
  onOpen,
  onSearch,
  selectedStake,
  symbols = [],
  api,
  gameId,
}: {
  cards: readonly ManagementCardState[];
  writeAllowed: boolean;
  busy: boolean;
  onOpen: (stake: ManagementStake) => void;
  onSearch: (stake: ManagementStake) => void;
  selectedStake?: number | null;
  symbols?: readonly SymbolResponse[];
  api?: Pick<ManagementGameClient, 'symbolImageAssetUrl'>;
  gameId?: string;
}) {
  return (
    <div className="management-tiles management-stake-cards">
      {cards.map(({ slot, status, error }) => (
        <button
          type="button"
          className="management-tile management-stake-choice"
          key={slot.stakeGrosze}
          aria-label={`Stawka ${formatZloty(slot.stakeGrosze)}`}
          aria-pressed={selectedStake === slot.stakeGrosze}
          data-selected={
            selectedStake === slot.stakeGrosze ? 'true' : undefined
          }
          disabled={busy || (!writeAllowed && slot.empty)}
          onClick={() =>
            writeAllowed ? onSearch(slot.stakeGrosze) : onOpen(slot.stakeGrosze)
          }
        >
          <strong>{formatZloty(slot.stakeGrosze)}</strong>
          <span>
            {slot.empty ? 'Brak zapisanego układu' : 'Zapisany układ'}
          </span>
          {slot.empty ? null : (
            <ManagementBoardPreview
              codes={slot.startSymbolCodes}
              symbols={symbols}
              api={api}
              gameId={gameId}
            />
          )}
          {status === 'checking' ? (
            <small role="status">Sprawdzanie…</small>
          ) : status === 'stale' ? (
            <small role="status">Wynik wymaga sprawdzenia</small>
          ) : null}
          {error ? <small role="alert">{error}</small> : null}
        </button>
      ))}
    </div>
  );
}
