'use client';

import type {
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

import { SuperGameStateBanner } from '../board-search-super-game-marker';

import type { SuperGameSeriesModalClient } from './super-game-series-client.ts';
import { SuperGameSeriesPanel } from './super-game-series-panel.tsx';
import {
  SERIES_STATE_POLL_INTERVAL_MS,
  isSeriesGenerationStale,
} from './super-game-series-state.ts';

/**
 * The series view of a marked board in a modal (D-564, TASK-1059): the
 * online share opens it from a super game marker. It owns which series is
 * open (the panel jumps to the next one without a symbol), polls the
 * freshness of the generation while it is stale and tells its host on close
 * whether anything was saved (a super symbol or a cell correction), so the
 * search can be read again. `Esc` belongs to the series view (it cancels a
 * symbol choice); the „Zamknij” button closes the modal.
 */
export interface SuperGameSeriesModalProps {
  readonly client: SuperGameSeriesModalClient;
  readonly gameId: string;
  /** The series of the marker that opened the modal. */
  readonly seriesId: string;
  /** The marked board: the carousel opens at it. */
  readonly initialSequenceNumber?: number | null;
  readonly symbols: readonly SymbolResponse[];
  readonly formatAmount?: (baseCredits: number) => string;
  /** `edited` is true when a super symbol or a cell correction was saved. */
  readonly onClose: (edited: boolean) => void;
}

export function SuperGameSeriesModal({
  client,
  formatAmount,
  gameId,
  initialSequenceNumber = null,
  onClose,
  seriesId: initialSeriesId,
  symbols,
}: SuperGameSeriesModalProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [seriesId, setSeriesId] = useState(initialSeriesId);
  const [edited, setEdited] = useState(false);
  // While a super symbol save is in flight the modal cannot be closed: a
  // late success would otherwise change the server without the host
  // reading its results again.
  const [saving, setSaving] = useState(false);
  const [generation, setGeneration] = useState<SuperGameStateResponse | null>(
    null,
  );
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    const opener =
      typeof document === 'undefined'
        ? null
        : (document.activeElement as HTMLElement | null);
    element?.showModal();
    return () => {
      element?.close();
      if (opener !== null && typeof opener.focus === 'function') {
        opener.focus();
      }
    };
  }, []);

  // While the generation is stale, its freshness is polled; when it becomes
  // fresh the opened series is read again (the Admin's list does the same).
  const stale = isSeriesGenerationStale(generation);
  useEffect(() => {
    if (!stale) return;
    const timer = window.setInterval(() => {
      void client
        .getSuperGameSeriesState(gameId)
        .then((result) => {
          if (result.data === undefined) return;
          setGeneration(result.data);
          if (result.data.fresh) setRefreshToken((token) => token + 1);
        })
        .catch(() => undefined);
    }, SERIES_STATE_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [client, gameId, stale]);

  return (
    <dialog
      aria-label="Seria supergry"
      className="superGameSeriesModal"
      onCancel={(event) => event.preventDefault()}
      ref={dialog}
    >
      <div className="superGameSeriesModalBody">
        <div className="superGameSeriesModalHeader">
          <div>
            <p className="eyebrow">Supergra</p>
            <h3>Seria supergry</h3>
          </div>
          <button
            className="secondaryButton"
            disabled={saving}
            onClick={() => onClose(edited)}
            title={saving ? 'Trwa zapis super symbolu.' : undefined}
            type="button"
          >
            {saving ? 'Zapisuję…' : 'Zamknij'}
          </button>
        </div>
        <SuperGameStateBanner state={generation} />
        <SuperGameSeriesPanel
          client={client}
          formatAmount={formatAmount}
          gameId={gameId}
          initialSequenceNumber={
            seriesId === initialSeriesId ? initialSequenceNumber : null
          }
          onBoardEdited={() => setEdited(true)}
          onSavingChange={setSaving}
          onSeriesChange={setSeriesId}
          onSeriesSaved={() => setEdited(true)}
          onSuperGameStateChange={setGeneration}
          refreshToken={refreshToken}
          seriesId={seriesId}
          symbols={symbols}
        />
      </div>
    </dialog>
  );
}
