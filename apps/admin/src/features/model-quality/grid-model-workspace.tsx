'use client';

import { useCallback, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { GridModelAssignmentSummary } from '@/features/games/grid-model-assignment-summary';
import { GridCohortPreview } from './grid-cohort-preview';
import { GridCorrectionLearningPanel } from './grid-correction-learning-panel';
import { GridModelComparison } from './grid-model-comparison';
import { GridModelVersionsPanel } from './grid-model-versions-panel';
import { GridQualityMeasurementPanel } from './grid-quality-measurement-panel';
import { GridReinferencePreview } from './grid-reinference-preview';
import { GridTrainingRunPanel } from './grid-training-run-panel';
import { RecordingGroupsPanel } from './recording-groups-panel';

/**
 * TASK-1000: the whole V3 geometry process of one game, in operator order. Entering the
 * section, changing the game or reloading only reads; every mutation is an explicit action
 * of a step. A confirmed change of one step re-reads the lists of the others (frozen
 * cohort, finished run, new version, activation) without a page reload. Human
 * corrections stay in the Reviewer.
 */
export function GridModelWorkspace({
  apiBaseUrl,
  gameId,
}: {
  readonly apiBaseUrl: string;
  readonly gameId: string;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const reinference = useRef<HTMLDetailsElement>(null);
  const scope = `${apiBaseUrl}:${gameId}`;
  const [refreshKey, setRefreshKey] = useState(0);
  const onChanged = useCallback(() => setRefreshKey((value) => value + 1), []);
  const shared = { apiBaseUrl, gameId, refreshKey, onChanged };
  return (
    <section className="modelQualityWorkflowGroup" aria-label="Geometria V3">
      <h2>Geometria V3</h2>
      <ol className="gridModelSteps">
        <li>Przypisana wersja</li>
        <li>Dostępne korekty i braki</li>
        <li>Uczenie i postęp</li>
        <li>Wynik i zastosowanie</li>
        <li>Historia</li>
      </ol>
      <GridModelAssignmentSummary
        key={`assignment:${scope}:${refreshKey}`}
        apiBaseUrl={apiBaseUrl}
        gameId={gameId}
      />
      <GridCorrectionLearningPanel
        key={`learning:${scope}`}
        apiBaseUrl={apiBaseUrl}
        gameId={gameId}
        onChanged={onChanged}
      />
      <button
        className="secondaryButton"
        type="button"
        onClick={() => {
          if (reinference.current) {
            reinference.current.open = true;
            reinference.current.scrollIntoView?.({
              behavior: 'smooth',
              block: 'start',
            });
          }
        }}
      >
        Propozycje siatek do ręcznej oceny
      </button>
      <details>
        <summary>Zaawansowane: nagrania, kohorty i parametry</summary>
        <RecordingGroupsPanel
          key={`recordings:${scope}`}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
          onChanged={onChanged}
        />
        <GridCohortPreview key={`cohorts:${scope}`} {...shared} />
        <GridTrainingRunPanel key={`runs:${scope}`} {...shared} />
        <GridModelComparison key={`comparison:${scope}`} {...shared} />
        <GridModelVersionsPanel key={`versions:${scope}`} {...shared} />
      </details>
      <details>
        <summary>Osobne narzędzie: kontrola jakości (próbka)</summary>
        <GridQualityMeasurementPanel
          key={`quality:${scope}`}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
        />
      </details>
      <details ref={reinference}>
        <summary>Osobne narzędzie: Ponowne rozpoznanie</summary>
        <GridReinferencePreview
          api={api}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
        />
      </details>
    </section>
  );
}
