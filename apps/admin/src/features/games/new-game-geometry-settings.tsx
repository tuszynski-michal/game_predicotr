'use client';

import type {
  GameGridModelAssignmentResponse,
  GridModelAssignmentCommand,
  GridModelDefaultResponse,
  GridModelVersionResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';
import type { GamesClient } from './game-catalog-actions';
import type { GameDraft } from './game-catalog-state';
import { PendingCommandRecovery } from './pending-command-recovery';

interface Props {
  readonly api: GamesClient;
  readonly apiBaseUrl: string;
  readonly draft: GameDraft;
  readonly gameId?: string;
  readonly disabled: boolean;
  readonly onChange: (draft: GameDraft) => void;
}

export function NewGameGeometrySettings({
  api,
  apiBaseUrl,
  draft,
  gameId,
  disabled,
  onChange,
}: Props) {
  const [versions, setVersions] = useState<readonly GridModelVersionResponse[]>(
    [],
  );
  const [defaultModel, setDefaultModel] =
    useState<GridModelDefaultResponse | null>(null);
  const [assignment, setAssignment] =
    useState<GameGridModelAssignmentResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [chosenVersion, setChosenVersion] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<GridModelAssignmentCommand | null>(
    null,
  );
  const namespace = `game-initial-assignment-v1:${apiBaseUrl}:${gameId ?? 'new'}`;

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() =>
        Promise.all([
          api.listGridModelVersions(),
          api.getGridModelDefault(),
          gameId === undefined
            ? Promise.resolve(null)
            : api.getGameGridModelAssignment(gameId),
        ]),
      )
      .then(([catalog, currentDefault, currentAssignment]) => {
        if (cancelled) return;
        if (
          catalog.error !== undefined ||
          currentDefault.error !== undefined ||
          currentAssignment?.error !== undefined ||
          catalog.data === undefined ||
          currentDefault.data === undefined
        ) {
          setError(
            'Nie udało się odczytać wersji geometrii. Ponownie otwórz formularz.',
          );
          setLoading(false);
          return;
        }
        setVersions(catalog.data);
        setDefaultModel(currentDefault.data);
        setAssignment(currentAssignment?.data ?? null);
        setLoading(false);
        const raw = localStorage.getItem(namespace);
        if (raw !== null) {
          const saved: GridModelAssignmentCommand = JSON.parse(raw);
          if (
            typeof saved.idempotencyKey !== 'string' ||
            typeof saved.versionId !== 'string' ||
            typeof saved.expectedRevision !== 'number'
          )
            throw new Error('Invalid saved assignment');
          setPending(saved);
          setChosenVersion(saved.versionId);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(
            'Nie można odczytać geometrii lub zapisanego polecenia przypisania.',
          );
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, namespace]);

  async function assignVersion() {
    if (gameId === undefined || saving || (!pending && !chosenVersion)) return;
    setSaving(true);
    setError('');
    try {
      const command =
        pending ??
        ({
          idempotencyKey: crypto.randomUUID(),
          versionId: chosenVersion,
          expectedRevision: assignment?.revision ?? 0,
          mode: assignment?.initialTransferAllowed
            ? 'initial_transfer'
            : 'evaluated',
        } satisfies GridModelAssignmentCommand);
      localStorage.setItem(namespace, JSON.stringify(command));
      if (localStorage.getItem(namespace) !== JSON.stringify(command))
        throw new Error('Storage unavailable');
      setPending(command);
      const result = await api.activateGameGridModel(gameId, command);
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się przypisać wersji. Zapisane polecenie można ponowić.',
          ),
        );
        return;
      }
      localStorage.removeItem(namespace);
      setPending(null);
      const current = await api.getGameGridModelAssignment(gameId);
      if (current.error !== undefined || current.data === undefined)
        throw new Error('Refresh unavailable');
      setAssignment(current.data);
      setNotice(
        'Przypisano wersję geometrii. Nowe zadania użyją tego przypisania.',
      );
    } catch {
      setError(
        'Przypisanie nie zostało potwierdzone. Ponów zapisane polecenie.',
      );
    } finally {
      setSaving(false);
    }
  }

  const eligible = versions.filter((version) => version.eligible);
  const selected = draft.gridModel;
  const mode = selected?.mode ?? 'default';
  const chosen = versions.find(
    (version) => version.manifest.versionId === chosenVersion,
  );
  return (
    <section aria-label="Geometria nowej gry">
      <p>
        Symbole są osobne dla każdej gry. Pierwszy import bez modelu wymaga co
        najmniej dwóch własnych aktywnych symboli.
      </p>
      {loading ? (
        <p>Sprawdzanie geometrii…</p>
      ) : defaultModel === null ? null : defaultModel.eligible ? (
        <p>
          Domyślna geometria: {defaultModel.version?.manifest.familyLabel} ·{' '}
          {defaultModel.version?.manifest.version}.
        </p>
      ) : (
        <p>
          Brak dopuszczonej domyślnej geometrii (
          {defaultModel?.reasonCode ?? 'brak odczytu'}). Gra może powstać bez
          przypisania. Import wymaga przypisanej wersji.
        </p>
      )}
      {error ? <p role="alert">{error}</p> : null}
      {gameId !== undefined ? (
        <PendingCommandRecovery
          namespace={namespace}
          refreshToken={`${saving}:${error}:${pending?.idempotencyKey ?? ''}`}
          onRecovered={() => {
            setPending(null);
            setChosenVersion('');
            setError('');
            setNotice(
              'Zachowano archiwum polecenia. Sprawdź aktualne przypisanie przed kolejną zmianą.',
            );
          }}
        />
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      <details>
        <summary>Zaawansowane: geometria</summary>
        {gameId === undefined ? (
          <>
            <label>
              Wybór geometrii
              <select
                name="gridModelMode"
                disabled={disabled || loading || !!error}
                value={mode}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  onChange({
                    ...draft,
                    gridModel:
                      value === 'default'
                        ? { mode: 'default' }
                        : value === 'published'
                          ? { mode: 'published', versionId: '' }
                          : {
                              mode: 'fork',
                              baseVersionId: '',
                              familyCode: '',
                              familyLabel: '',
                            },
                  });
                }}
              >
                <option value="default">Domyślna wersja</option>
                <option value="published">Opublikowana wersja</option>
                <option value="fork">Nowa rodzina z opublikowanej bazy</option>
              </select>
            </label>
            {mode !== 'default' ? (
              <label>
                Wersja bazowa
                <select
                  name="gridModelBase"
                  disabled={disabled || loading}
                  value={
                    selected?.mode === 'published'
                      ? selected.versionId
                      : selected?.mode === 'fork'
                        ? selected.baseVersionId
                        : ''
                  }
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      gridModel:
                        selected?.mode === 'fork'
                          ? {
                              ...selected,
                              baseVersionId: event.currentTarget.value,
                            }
                          : {
                              mode: 'published',
                              versionId: event.currentTarget.value,
                            },
                    })
                  }
                  required
                >
                  <option value="">Wybierz wersję</option>
                  {eligible.map(({ manifest }) => (
                    <option key={manifest.versionId} value={manifest.versionId}>
                      {manifest.familyLabel} · {manifest.version}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {selected?.mode === 'fork' ? (
              <>
                <label>
                  Kod nowej rodziny
                  <input
                    required
                    disabled={disabled}
                    name="gridModelFamilyCode"
                    value={selected.familyCode}
                    pattern="[a-z][a-z0-9_]{0,63}"
                    maxLength={64}
                    onChange={(event) =>
                      onChange({
                        ...draft,
                        gridModel: {
                          ...selected,
                          familyCode: event.currentTarget.value,
                        },
                      })
                    }
                  />
                </label>
                <label>
                  Nazwa nowej rodziny
                  <input
                    required
                    disabled={disabled}
                    name="gridModelFamilyLabel"
                    value={selected.familyLabel}
                    maxLength={200}
                    onChange={(event) =>
                      onChange({
                        ...draft,
                        gridModel: {
                          ...selected,
                          familyLabel: event.currentTarget.value,
                        },
                      })
                    }
                  />
                </label>
                <p>
                  Nowa rodzina dziedziczy bazę i wyłączenia danych. Wagi i
                  etykiety nie są kopiowane.
                </p>
              </>
            ) : null}
            {selected?.mode === 'published' ? (
              <p>Rodzina treningowa będzie rodziną wybranej wersji.</p>
            ) : null}
          </>
        ) : (
          <>
            <p>
              Przypisana wersja:{' '}
              {assignment?.version
                ? `${assignment.version.manifest.familyLabel} · ${assignment.version.manifest.version}`
                : 'brak'}
              .
            </p>
            <p>
              Rodzina treningowa:{' '}
              {assignment?.trainingFamilyLabel ??
                assignment?.version?.manifest.familyLabel ??
                'brak'}
              .
            </p>
            <label>
              Opublikowana wersja
              <select
                name="gridModelAssignmentVersion"
                disabled={disabled || loading || saving || pending !== null}
                value={chosenVersion}
                onChange={(event) =>
                  setChosenVersion(event.currentTarget.value)
                }
              >
                <option value="">Wybierz wersję</option>
                {eligible.map(({ manifest }) => (
                  <option key={manifest.versionId} value={manifest.versionId}>
                    {manifest.familyLabel} · {manifest.version}
                  </option>
                ))}
              </select>
            </label>
            {chosen ? (
              <p>
                Po przypisaniu rodzina treningowa: {chosen.manifest.familyLabel}
                . Dotychczasowy fork pozostaje w historii.
              </p>
            ) : null}
            <p>
              {assignment?.initialTransferAllowed
                ? 'Pierwsze przypisanie przenosi zgodną bazę. Nie oznacza pomiaru jakości tej gry.'
                : 'Aktywacja wymaga aktualnej oceny obejmującej tę grę.'}
            </p>
            <button
              type="button"
              disabled={
                disabled ||
                loading ||
                saving ||
                (!chosenVersion && pending === null)
              }
              onClick={() => void assignVersion()}
            >
              {pending
                ? 'Ponów zapisane przypisanie'
                : 'Przypisz wybraną wersję'}
            </button>
          </>
        )}
      </details>
    </section>
  );
}
