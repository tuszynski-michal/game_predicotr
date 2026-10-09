'use client';

import type {
  ManagementStake,
  ManagementStakeResponse,
} from '@game-predictor/admin-api-client';
import { formatZloty } from '../index';
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

/** Immutable start-symbol preview; no current-board or image requests from cards. */
export function ManagementBoardPreview({
  codes,
}: {
  codes: readonly (string | null)[] | null | undefined;
}) {
  return (
    <div
      className="management-board-preview"
      aria-label="Symbole zapisanej planszy"
    >
      {Array.from({ length: 15 }, (_, index) => (
        <span key={index}>{codes?.[index] ?? '?'}</span>
      ))}
    </div>
  );
}

/** Backend bounds this authoritative preview to 256 points; do not invent payout rows. */
function ManagementMiniChart({ slot }: { slot: ManagementStakeResponse }) {
  const points = slot.chartPoints ?? [];
  if (!points.length) return <p>Brak zapisanego wykresu.</p>;
  const low = Math.min(0, ...points.map((point) => point.balanceCredits));
  const high = Math.max(0, ...points.map((point) => point.balanceCredits));
  const end = Math.max(1, ...points.map((point) => point.spinNumber));
  const x = (spin: number) => 12 + (spin / end) * 276;
  const y = (balance: number) =>
    110 - ((balance - low) / Math.max(1, high - low)) * 100;
  return (
    <svg
      className="management-mini-chart"
      viewBox="0 0 300 128"
      role="img"
      aria-label={`Zapisany bilans dla stawki ${formatZloty(slot.stakeGrosze)}`}
    >
      <title>Ostatni zapisany wynik, {end} spinów</title>
      <line
        x1="12"
        y1={y(0)}
        x2="288"
        y2={y(0)}
        className="boardSearchApproximateWinChartZero"
      />
      <polyline
        points={points
          .map((point) => `${x(point.spinNumber)},${y(point.balanceCredits)}`)
          .join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      {(slot.pinnedPoints ?? [])
        .filter((point) => point.available)
        .map((point) => (
          <circle
            key={point.spinNumber}
            cx={x(point.spinNumber)}
            cy={y(point.balanceCredits)}
            r="4"
          >
            <title>
              Spin {point.spinNumber}:{' '}
              {managementAmount(
                point.balanceCredits,
                slot.stakeGrosze,
                slot.spinCost ?? 0,
              )}
            </title>
          </circle>
        ))}
    </svg>
  );
}

export function ManagementCards({
  cards,
  writeAllowed,
  busy,
  onOpen,
  onSearch,
  onClear,
  selectedStake,
}: {
  cards: readonly ManagementCardState[];
  writeAllowed: boolean;
  busy: boolean;
  onOpen: (stake: ManagementStake) => void;
  onSearch: (stake: ManagementStake) => void;
  onClear: (stake: ManagementStake) => void;
  selectedStake?: number | null;
}) {
  return (
    <div className="management-tiles management-stake-cards">
      {cards.map(({ slot, status, error }) => (
        <article
          className="management-tile"
          key={slot.stakeGrosze}
          aria-label={`Stawka ${formatZloty(slot.stakeGrosze)}`}
          data-selected={
            selectedStake === slot.stakeGrosze ? 'true' : undefined
          }
        >
          <h4>{formatZloty(slot.stakeGrosze)}</h4>
          {slot.empty ? (
            <p>Brak zapisanego układu.</p>
          ) : (
            <>
              <p>
                Plansza #{slot.startSequenceNumber} ·{' '}
                {slot.spinCount?.toLocaleString('pl-PL')} spinów
              </p>
              <ManagementBoardPreview codes={slot.startSymbolCodes} />
              <ManagementMiniChart slot={slot} />
              <p>
                Bilans:{' '}
                {slot.summary
                  ? managementAmount(
                      slot.summary.balanceCredits,
                      slot.stakeGrosze,
                      slot.spinCost ?? 0,
                    )
                  : '—'}
              </p>
              <p>Zapisano: {managementDate(slot.savedAt)}</p>
              {(slot.pinnedPoints ?? []).length ? (
                <ul aria-label="Zapisane przypięte punkty">
                  {slot.pinnedPoints?.map((point) => (
                    <li key={point.spinNumber}>
                      Spin {point.spinNumber}:{' '}
                      {point.available
                        ? managementAmount(
                            point.balanceCredits,
                            slot.stakeGrosze,
                            slot.spinCost ?? 0,
                          )
                        : 'niedostępny'}
                    </li>
                  ))}
                </ul>
              ) : null}
              {(slot.unavailablePinPositions ?? [])
                .filter(
                  (spin) =>
                    !slot.pinnedPoints?.some(
                      (point) => point.spinNumber === spin,
                    ),
                )
                .map((spin) => (
                  <p key={spin}>Spin {spin}: niedostępny</p>
                ))}
            </>
          )}
          <p role="status">
            {status === 'checking'
              ? 'Sprawdzanie bieżących danych… Poprzedni wynik pozostaje widoczny.'
              : status === 'stale'
                ? 'Wynik nieaktualny. Zachowano poprzedni wynik.'
                : status === 'current'
                  ? 'Wynik zgodny z bieżącymi danymi.'
                  : 'Pusta stawka.'}
          </p>
          {error ? <p role="alert">{error}</p> : null}
          <div className="management-actions">
            <button
              disabled={busy || slot.empty}
              onClick={() => onOpen(slot.stakeGrosze)}
            >
              Otwórz
            </button>
            <button
              disabled={busy || !writeAllowed}
              onClick={() => onSearch(slot.stakeGrosze)}
            >
              {slot.empty ? 'Wyszukaj układ' : 'Szukaj ponownie'}
            </button>
            <button
              disabled={busy || !writeAllowed || slot.empty}
              onClick={() => onClear(slot.stakeGrosze)}
            >
              Wyczyść
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
