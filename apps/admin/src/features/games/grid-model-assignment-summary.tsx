'use client';

import type {
  AdminApiClient,
  GameGridModelAssignmentResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

type AssignmentClient = Pick<AdminApiClient, 'getGameGridModelAssignment'>;
interface Props {
  readonly apiBaseUrl: string;
  readonly client?: AssignmentClient;
  readonly gameId: string;
}

export function GridModelAssignmentSummary(props: Props) {
  return <AssignmentRead key={props.gameId} {...props} />;
}

function AssignmentRead({ apiBaseUrl, client, gameId }: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [result, setResult] = useState<{
    readonly api: AssignmentClient;
    readonly assignment?: GameGridModelAssignmentResponse;
    readonly error?: string;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => api.getGameGridModelAssignment(gameId))
      .then((response) => {
        if (cancelled) return;
        if (
          response.error !== undefined ||
          response.data === undefined ||
          response.data.version === undefined ||
          response.data.gameId !== gameId
        ) {
          setResult({
            api,
            error: 'Nie udało się odczytać przypisanej geometrii.',
          });
          return;
        }
        setResult({ api, assignment: response.data });
      })
      .catch(() => {
        if (!cancelled)
          setResult({
            api,
            error: 'Nie udało się odczytać przypisanej geometrii.',
          });
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  if (result === null || result.api !== api)
    return <span aria-busy="true">Sprawdzanie przypisanej geometrii V3…</span>;
  if (result.error)
    return (
      <span role="alert">
        {result.error} Odśwież widok, aby ponowić odczyt.
      </span>
    );
  const version = result.assignment?.version;
  if (!version)
    return (
      <span>
        Brak przypisanej wersji geometrii V3. Import wymaga przypisania wersji.
      </span>
    );
  const stale =
    version.eligibilityReasonCode === 'GRID_MODEL_EVALUATION_STALE' ||
    version.eligibilityReasonCode === 'GRID_MODEL_PUBLICATION_STALE';
  return (
    <span>
      Geometria V3: {version.manifest.familyLabel} · {version.manifest.version}
      {' · '}
      {version.manifest.versionId}
      <br />
      {version.available
        ? 'Artefakty przypisanej wersji dostępne.'
        : `Artefakty przypisanej wersji niedostępne (${version.reasonCode}).`}
      {stale ? (
        <>
          {' '}
          Dowód oceny jest nieaktualny ({version.eligibilityReasonCode}).
          Przypisanie pozostaje zachowane.
        </>
      ) : null}{' '}
      Gotowość importu sprawdza preflight.
    </span>
  );
}
