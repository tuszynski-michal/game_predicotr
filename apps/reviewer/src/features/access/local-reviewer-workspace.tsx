'use client';

import type { AdminApiClient } from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';

import { GridReviewWorkspace } from '@/features/grid-reviews/grid-review-workspace';
import { OperationalReviewWorkspace } from '@/features/operational-reviews/operational-review-workspace';

import {
  initialLocalReviewerWorkspaceMode,
  type LocalReviewerWorkspaceMode,
} from './local-reviewer-workspace-state';

export function LocalReviewerWorkspace({
  api,
  apiBaseUrl,
  gameId,
  importJobId,
}: {
  readonly api: AdminApiClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly importJobId: string;
}) {
  const [mode, setMode] = useState<LocalReviewerWorkspaceMode | null>(null);
  const [gridReviewCount, setGridReviewCount] = useState(0);
  const [deferredGeometryCount, setDeferredGeometryCount] = useState(0);
  const [diagnosticError, setDiagnosticError] = useState('');

  useEffect(() => {
    let active = true;
    setMode(null);
    setDiagnosticError('');
    void Promise.all([
      api.listImageGridReviews({ gameId, importJobId, limit: 1, view: 'all' }),
      api.listPendingBoardCellGeometry({
        gameId,
        importJobId,
        limit: 1,
        status: 'pending',
      }),
    ])
      .then(([gridResult, deferredResult]) => {
        if (!active) return;
        if (
          gridResult.error !== undefined ||
          gridResult.data === undefined ||
          deferredResult.error !== undefined ||
          deferredResult.data === undefined
        ) {
          setDiagnosticError(
            'Nie udało się odczytać obu kolejek. Otwieram standardową walidację geometrii.',
          );
          setMode('grid');
          return;
        }
        const gridCount = gridResult.data.counts.total;
        const deferredCount = deferredResult.data.counts.pending;
        setGridReviewCount(gridCount);
        setDeferredGeometryCount(deferredCount);
        setMode(initialLocalReviewerWorkspaceMode(gridCount, deferredCount));
      })
      .catch(() => {
        if (!active) return;
        setDiagnosticError(
          'Połączenie z kolejkami geometrii zostało przerwane. Otwieram standardową walidację.',
        );
        setMode('grid');
      });
    return () => {
      active = false;
    };
  }, [api, gameId, importJobId]);

  if (mode === null) {
    return (
      <section className="localReviewerModeLoading" role="status">
        <strong>Sprawdzam kolejki geometrii…</strong>
        <span>Wybieram właściwy edytor dla tego importu.</span>
      </section>
    );
  }

  return (
    <>
      <nav
        className="localReviewerModeSwitch"
        aria-label="Tryb korekty geometrii"
      >
        <button
          aria-pressed={mode === 'grid'}
          className={mode === 'grid' ? 'isActive' : undefined}
          onClick={() => setMode('grid')}
          type="button"
        >
          Walidacja gotowych siatek ({gridReviewCount.toLocaleString('pl-PL')})
        </button>
        <button
          aria-pressed={mode === 'deferred'}
          className={mode === 'deferred' ? 'isActive' : undefined}
          disabled={deferredGeometryCount === 0}
          onClick={() => setMode('deferred')}
          type="button"
        >
          Niepełne siatki do ręcznej korekty (
          {deferredGeometryCount.toLocaleString('pl-PL')})
        </button>
      </nav>
      {diagnosticError ? (
        <p className="localReviewerModeError" role="alert">
          {diagnosticError}
        </p>
      ) : null}
      {mode === 'grid' ? (
        <GridReviewWorkspace
          apiBaseUrl={apiBaseUrl}
          client={api}
          gameId={gameId}
          importJobId={importJobId}
        />
      ) : (
        <OperationalReviewWorkspace
          apiBaseUrl={apiBaseUrl}
          client={api}
          gameId={gameId}
          importJobId={importJobId}
        />
      )}
    </>
  );
}
