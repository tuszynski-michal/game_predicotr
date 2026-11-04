'use client';

import { useMemo, useState, useRef } from 'react';
import type {
  GridCohortHeader,
  GridModelEvaluationCohortPin,
} from '@game-predictor/admin-api-client';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { GridCohortPreview } from './grid-cohort-preview';
import { cohortLabel } from './grid-model-state';

/** Explicit replacement of an already required OTHER game; no newest selection. */
export function GridHistoryRecovery({
  apiBaseUrl,
  gameIds,
  selected,
  onChange,
  disabled,
  trainingMode,
  policyVersion,
  gameLabels,
}: {
  readonly apiBaseUrl: string;
  readonly gameIds: readonly string[];
  readonly selected: readonly GridModelEvaluationCohortPin[];
  readonly onChange: (value: GridModelEvaluationCohortPin[]) => void;
  readonly disabled: boolean;
  readonly trainingMode: 'grid-only' | 'screen+grid';
  readonly policyVersion:
    'application-grid-corrections-v3' | 'application-grid-corrections-v4';
  readonly gameLabels?: Readonly<Record<string, string>>;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [rows, setRows] = useState<Record<string, GridCohortHeader[]>>({});
  const [next, setNext] = useState<Record<string, string | null>>({});
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [preparing, setPreparing] = useState<string | null>(null);
  async function load(game: string, cursor?: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.listGridTrainingCohorts(game, {
        limit: 50,
        ...(cursor ? { cursor } : {}),
      });
      if (!result.data || result.data.items.some((x) => x.gameId !== game))
        throw new Error('Nie udało się odczytać kohort tej gry.');
      const data = result.data;
      setRows((old) => ({
        ...old,
        [game]: cursor ? [...(old[game] ?? []), ...data.items] : data.items,
      }));
      setNext((old) => ({ ...old, [game]: data.nextCursor }));
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  }
  return (
    <section aria-label="Zastąpienie historycznej kohorty">
      <p>
        Wyłącznie już wymagane inne gry. Pozostaw wybór pusty, aby zachować
        przypiętą historię. Stary grid-only lub screen bez wymaganej polityki
        nie oznacza złych punktów: przygotuj i zamroź nową zgodną kohortę{' '}
        {policyVersion.endsWith('v4') ? 'v4' : 'v3'} z istniejących GT, bez
        ponownego rysowania i bez startu treningu.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {gameIds.map((game) => (
        <fieldset key={game} disabled={disabled || busy}>
          <legend>Wymagana gra {gameLabels?.[game] ?? 'inna gra'}</legend>
          <button
            className="secondaryButton"
            type="button"
            aria-busy={busy}
            onClick={() => void load(game)}
          >
            {busy ? 'Odczytywanie…' : 'Odczytaj kohorty tej gry'}
          </button>
          {next[game] ? (
            <button
              className="secondaryButton"
              type="button"
              onClick={() => void load(game, next[game]!)}
            >
              Odczytaj dalsze kohorty
            </button>
          ) : null}
          <select
            aria-label={`Kohorta gry ${game}`}
            value={selected.find((x) => x.gameId === game)?.cohortId ?? ''}
            onChange={(event) => {
              const cohort = rows[game]?.find(
                (x) => x.id === event.target.value,
              );
              onChange(
                [
                  ...selected.filter((x) => x.gameId !== game),
                  ...(cohort?.manifestSha256
                    ? [
                        {
                          gameId: game,
                          cohortId: cohort.id,
                          manifestSha256: cohort.manifestSha256,
                        },
                      ]
                    : []),
                ].sort((a, b) => a.gameId.localeCompare(b.gameId)),
              );
            }}
          >
            <option value="">Zachowaj przypiętą historię</option>
            {(rows[game] ?? [])
              .filter(
                (x) =>
                  x.status === 'frozen' &&
                  x.mode === trainingMode &&
                  x.policyVersion === policyVersion &&
                  x.manifestSha256,
              )
              .map((x) => (
                <option key={x.id} value={x.id}>
                  {cohortLabel(x)}
                </option>
              ))}
          </select>
          <button
            type="button"
            className="secondaryButton"
            onClick={() => setPreparing(preparing === game ? null : game)}
          >
            Przygotuj nową kohortę z istniejących GT
          </button>
        </fieldset>
      ))}
      {preparing && gameIds.includes(preparing) ? (
        <GridCohortPreview
          key={preparing}
          apiBaseUrl={apiBaseUrl}
          gameId={preparing}
          correctionRecovery
          correctionMode={trainingMode}
          correctionPolicyVersion={policyVersion}
        />
      ) : null}
      <p>
        Wybór jest propozycją dla następnego podglądu. Backend nadal sprawdza
        aktualność, zgodność bazy, role i pełne TRAIN/A; żadna gra nie jest
        automatycznie dodawana ani usuwana.
      </p>
    </section>
  );
}
