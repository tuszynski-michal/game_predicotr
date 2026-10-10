'use client';

import type { AdminApiClient } from '@game-predictor/admin-api-client';
import { useState } from 'react';

import { BoardGeometryCorrectionWorkspace } from '@/features/operational-reviews/board-geometry-correction-workspace';
import { GeometryGapsWorkspace } from '@/features/operational-reviews/geometry-gaps-workspace';

type LocalReviewerTab = 'correction' | 'gaps';

/**
 * The local Reviewer (port 3001) is the single grid-correction screen of
 * D-462: one queue, one board at a time, no validation of finished grids.
 * TASK-0962: it works on the whole game (the import is optional) and has two
 * tabs: the board queue "Do korekty" and the image-level "Braki zdjęć"
 * (TASK-0963). Both panels stay mounted, so switching tabs never discards
 * the board the operator is editing; the hidden panel only stops listening
 * to keys.
 */
export function LocalReviewerWorkspace({
  api,
  apiBaseUrl,
  gameId,
  importJobId,
}: {
  readonly api: AdminApiClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly importJobId?: string | undefined;
}) {
  const [tab, setTab] = useState<LocalReviewerTab>('correction');
  return (
    <>
      <div
        aria-label="Widok lokalnego Reviewera"
        className="reviewerTabs"
        role="tablist"
      >
        <button
          aria-controls="reviewer-tab-correction"
          aria-selected={tab === 'correction'}
          className="secondaryButton"
          id="reviewer-tab-correction-button"
          onClick={() => setTab('correction')}
          role="tab"
          type="button"
        >
          Do korekty
        </button>
        <button
          aria-controls="reviewer-tab-gaps"
          aria-selected={tab === 'gaps'}
          className="secondaryButton"
          id="reviewer-tab-gaps-button"
          onClick={() => setTab('gaps')}
          role="tab"
          type="button"
        >
          Braki zdjęć
        </button>
      </div>
      <div
        aria-labelledby="reviewer-tab-correction-button"
        className="reviewerTabPanel"
        hidden={tab !== 'correction'}
        id="reviewer-tab-correction"
        role="tabpanel"
      >
        <BoardGeometryCorrectionWorkspace
          api={api}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
          importJobId={importJobId}
          keyboardEnabled={tab === 'correction'}
        />
      </div>
      <div
        aria-labelledby="reviewer-tab-gaps-button"
        className="reviewerTabPanel"
        hidden={tab !== 'gaps'}
        id="reviewer-tab-gaps"
        role="tabpanel"
      >
        <GeometryGapsWorkspace
          api={api}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
          keyboardEnabled={tab === 'gaps'}
        />
      </div>
    </>
  );
}
