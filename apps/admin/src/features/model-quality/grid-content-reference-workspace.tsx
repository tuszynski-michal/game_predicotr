'use client';

import type {
  AdminApiClient,
  ContentReadinessResponse,
  ContentTargetResponse,
  GridCohortHeader,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import { GridContentBlind } from './grid-content-blind';
import { GridContentOrdinary } from './grid-content-ordinary';
import { GridContentReadiness } from './grid-content-readiness';
import { reasonLabel } from './grid-model-state';
import {
  contentRoleLabel,
  type ContentCommand,
  type ContentMode,
} from './grid-content-state';

export type GridContentClient = Pick<
  AdminApiClient,
  | 'listGridTrainingCohorts'
  | 'listGridContentTargets'
  | 'gridContentTargetSourceUrl'
  | 'getGridCellContentReference'
  | 'writeGridCellContentReference'
  | 'getGridContentReadiness'
  | 'listGridContentSessions'
  | 'getGridContentSession'
  | 'createGridContentSession'
  | 'writeGridBlindContentObservation'
  | 'advanceGridContentSession'
  | 'gridContentSessionSourceUrl'
>;

export function GridContentReferenceWorkspace(props: {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly mode: ContentMode;
  readonly onClose: () => void;
  readonly client?: GridContentClient;
}) {
  return (
    <ContentWorkspace
      key={`${props.apiBaseUrl}:${props.gameId}:${props.mode}`}
      {...props}
    />
  );
}

function ContentWorkspace({
  apiBaseUrl,
  gameId,
  mode,
  onClose,
  client,
}: Parameters<typeof GridContentReferenceWorkspace>[0]) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [client, apiBaseUrl],
  );
  return (
    <section
      className="gridContentWorkflow"
      aria-label="Etykietowanie zawartości"
    >
      <h2>
        {mode === 'blind'
          ? 'Pomiar powtarzalności etykiet'
          : 'Etykiety zawartości pól'}
      </h2>
      <p>
        {mode === 'blind'
          ? 'Pozostałe narzędzia geometrii są ukryte na czas tego pomiaru.'
          : 'Zwykłe etykiety są niezależne od geometrii. Zapis nie uruchamia treningu ani zastosowania modelu.'}
      </p>
      <button className="secondaryButton" type="button" onClick={onClose}>
        Wróć do panelu geometrii
      </button>
      {mode === 'blind' ? (
        <GridContentBlind api={api} apiBaseUrl={apiBaseUrl} gameId={gameId}>
          {(create, blocked) => (
            <ContentTargetSelection
              api={api}
              gameId={gameId}
              mode="blind"
              create={create}
              blocked={blocked}
            />
          )}
        </GridContentBlind>
      ) : (
        <ContentTargetSelection
          api={api}
          gameId={gameId}
          apiBaseUrl={apiBaseUrl}
          mode="ordinary"
        />
      )}
    </section>
  );
}

function ContentTargetSelection({
  api,
  gameId,
  apiBaseUrl = '',
  mode,
  create,
  blocked = false,
}: {
  readonly api: GridContentClient;
  readonly gameId: string;
  readonly apiBaseUrl?: string;
  readonly mode: ContentMode;
  readonly create?: (command: ContentCommand) => void;
  readonly blocked?: boolean;
}) {
  const [cohorts, setCohorts] = useState<GridCohortHeader[]>([]);
  const [nextCohort, setNextCohort] = useState<string | null>(null);
  const [cohort, setCohort] = useState<GridCohortHeader | null>(null);
  const [targets, setTargets] = useState<ContentTargetResponse[]>([]);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [selection, setSelection] = useState<
    Record<string, ContentTargetResponse>
  >({});
  const [chosen, setChosen] = useState<ContentTargetResponse | null>(null);
  const [readiness, setReadiness] = useState<ContentReadinessResponse | null>(
    null,
  );
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const alive = useRef(true);
  const listLock = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  async function listCohorts(cursor?: string) {
    if (listLock.current) return;
    listLock.current = true;
    setReading(true);
    setError('');
    try {
      const result = await api.listGridTrainingCohorts(gameId, {
        limit: 20,
        cursor,
      });
      if (!alive.current) return;
      if (!result.data)
        throw new Error(
          apiErrorMessage(result.error, 'Nie udało się odczytać kohort.'),
        );
      if (result.data.items.some((c) => c.gameId !== gameId))
        throw new Error('Odrzucono kohorty innej gry.');
      setCohorts(result.data.items);
      setNextCohort(result.data.nextCursor);
    } catch (failure) {
      if (alive.current) setError(String(failure));
    } finally {
      listLock.current = false;
      if (alive.current) setReading(false);
    }
  }
  useEffect(() => {
    void Promise.resolve().then(() => {
      if (alive.current) void listCohorts();
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setTargets([]);
      setNextOffset(null);
      setChosen(null);
      if (!cohort?.manifestSha256) return;
      setReading(true);
      setError('');
      void api
        .listGridContentTargets(gameId, {
          cohortId: cohort.id,
          manifestSha256: cohort.manifestSha256,
          offset,
          limit: 20,
        })
        .then((result) => {
          if (!active) return;
          if (!result.data)
            throw new Error(
              apiErrorMessage(
                result.error,
                'Nie udało się odczytać zdjęć i plansz.',
              ),
            );
          if (
            result.data.gameId !== gameId ||
            result.data.cohortId !== cohort.id ||
            result.data.manifestSha256 !== cohort.manifestSha256
          )
            throw new Error('Odrzucono cele innej gry lub wersji kohorty.');
          setTargets(result.data.items);
          setNextOffset(result.data.nextOffset);
        })
        .catch((failure) => {
          if (active) setError(String(failure));
        })
        .finally(() => {
          if (active) setReading(false);
        });
    });
    return () => {
      active = false;
    };
  }, [api, gameId, cohort, offset, refresh]);
  async function readCoverage() {
    if (!cohort?.manifestSha256 || reading) return;
    setReading(true);
    setError('');
    setReadiness(null);
    try {
      const result = await api.getGridContentReadiness(
        gameId,
        cohort.id,
        cohort.manifestSha256,
      );
      if (!alive.current) return;
      if (!result.data)
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie udało się sprawdzić pokrycia etykietami.',
          ),
        );
      setReadiness(result.data);
    } catch (failure) {
      if (alive.current) setError(String(failure));
    } finally {
      if (alive.current) setReading(false);
    }
  }
  const selected = Object.values(selection);
  const photoCount = new Set(selected.map((t) => t.source.sourceId)).size;
  return (
    <section
      className="gridContentWorkflow"
      aria-label="Wybór zdjęć do etykietowania"
    >
      <h3>
        {mode === 'blind' ? 'Nowa sesja pomiaru' : 'Wybierz zdjęcie i planszę'}
      </h3>
      {error ? <p role="alert">{error}</p> : null}
      <div className="gridContentActions">
        <button
          className="secondaryButton"
          type="button"
          disabled={reading || blocked}
          aria-busy={reading}
          onClick={() => void listCohorts()}
        >
          {reading ? 'Odczytywanie…' : 'Odśwież listę zestawów'}
        </button>
        <label>
          Zamrożony zestaw{' '}
          <select
            aria-label="Zamrożony zestaw etykiet"
            value={cohort?.id ?? ''}
            disabled={reading || blocked}
            onChange={(e) => {
              setCohort(cohorts.find((c) => c.id === e.target.value) ?? null);
              setOffset(0);
              setSelection({});
              setReadiness(null);
              setChosen(null);
            }}
          >
            <option value="">Wybierz zestaw</option>
            {cohorts
              .filter((c) => c.status === 'frozen' && c.manifestSha256)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {new Date(c.createdAt).toLocaleDateString('pl-PL')} ·{' '}
                  {c.mode === 'screen+grid' ? 'Detektor i siatka' : 'Siatka'} ·
                  rewizja {c.revision} ·{' '}
                  {c.summary.roles.reduce(
                    (n, r) => n + (r.materializedPhotos ?? r.eligiblePhotos),
                    0,
                  )}{' '}
                  zdjęć
                </option>
              ))}
          </select>
        </label>
        {nextCohort ? (
          <button
            className="secondaryButton"
            type="button"
            disabled={reading || blocked}
            onClick={() => void listCohorts(nextCohort)}
          >
            Kolejne zestawy
          </button>
        ) : null}
      </div>
      {!cohorts.some((c) => c.status === 'frozen' && c.manifestSha256) &&
      !reading ? (
        <p>
          Na tej stronie nie ma zamrożonych zestawów. Przygotuj zestaw w
          zaawansowanych narzędziach geometrii lub odczytaj kolejną stronę.
        </p>
      ) : null}
      {cohort ? (
        <>
          <div className="gridContentActions">
            <button
              type="button"
              className="secondaryButton"
              disabled={reading || blocked}
              aria-busy={reading}
              onClick={() => {
                setRefresh((v) => v + 1);
                setReadiness(null);
              }}
            >
              Odśwież zdjęcia i plansze
            </button>
            {mode === 'ordinary' ? (
              <button
                type="button"
                className="secondaryButton"
                disabled={reading || blocked}
                onClick={() => void readCoverage()}
              >
                Sprawdź pokrycie etykietami
              </button>
            ) : null}
          </div>
          <ul className="gridContentTargets" aria-label="Zdjęcia i plansze">
            {targets.map((target) => {
              const key = `${target.source.sourceId}:${target.positionIndex}`;
              const displayName = target.displayName || 'Zdjęcie bez nazwy';
              const allowed =
                target.state === 'ready' &&
                target.sequenceNumber != null &&
                target.sequenceNumber > 0 &&
                (mode !== 'blind' ||
                  target.role === 'TRAIN' ||
                  target.role === 'A');
              return (
                <li key={key}>
                  <span>
                    {displayName} · {contentRoleLabel(target.role)} · pozycja{' '}
                    {target.positionIndex + 1} · numer planszy{' '}
                    {target.sequenceNumber ?? 'nieustalona'}
                  </span>
                  {!allowed ? (
                    <span>
                      Nie można wybrać:{' '}
                      {target.reasonCodes.map(reasonLabel).join('; ') ||
                        'Pomiar obejmuje wyłącznie zdjęcia treningowe i zdjęcia do wyboru modelu.'}
                    </span>
                  ) : mode === 'blind' ? (
                    <label>
                      <input
                        type="checkbox"
                        aria-label={`Wybierz ${displayName} pozycja ${target.positionIndex + 1}`}
                        disabled={blocked || reading}
                        checked={Boolean(selection[key])}
                        onChange={(e) =>
                          setSelection((old) => {
                            const next = { ...old };
                            if (e.target.checked) next[key] = target;
                            else delete next[key];
                            return next;
                          })
                        }
                      />{' '}
                      Dodaj planszę do pomiaru
                    </label>
                  ) : (
                    <button
                      type="button"
                      className="secondaryButton"
                      disabled={reading || blocked}
                      onClick={() => setChosen(target)}
                    >
                      Oznacz {displayName} — pozycja {target.positionIndex + 1}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          {!targets.length && !reading ? (
            <p>Brak plansz w tym zakresie.</p>
          ) : null}
          <div className="gridContentActions">
            {offset > 0 ? (
              <button
                className="secondaryButton"
                type="button"
                disabled={reading || blocked}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Poprzednie plansze
              </button>
            ) : null}
            {nextOffset !== null ? (
              <button
                className="secondaryButton"
                type="button"
                disabled={reading || blocked}
                onClick={() => setOffset(nextOffset)}
              >
                Kolejne plansze
              </button>
            ) : null}
          </div>
          {mode === 'blind' ? (
            <>
              <p>
                Wybrano {selected.length} plansz na {photoCount} zdjęciach.
                Pomiar powtarzalności wymaga co najmniej 30 plansz na 10
                zdjęciach. Wybór jest jawny i pozostanie taki sam w obu
                przebiegach.
              </p>
              <p>
                Pomiar dla aktualnego sposobu wycinania. Ustawienia zostaną
                przypięte na początku sesji.
              </p>
              <button
                type="button"
                className="primaryButton"
                disabled={reading || blocked || !selected.length}
                onClick={() => {
                  if (!cohort.manifestSha256) return;
                  const sources = [
                    ...new Set(selected.map((t) => t.source.sourceId)),
                  ];
                  create?.({
                    kind: 'create',
                    body: {
                      idempotencyKey: crypto.randomUUID(),
                      cohortId: cohort.id,
                      expectedManifestSha256: cohort.manifestSha256,
                      sourceIds: sources,
                      renderReferencePolicy: 'active-symbol-render-v2',
                      targetSelection: sources.map((sourceId) => ({
                        sourceId,
                        positionIndices: selected
                          .filter((t) => t.source.sourceId === sourceId)
                          .map((t) => t.positionIndex)
                          .sort((a, b) => a - b),
                      })),
                    },
                  });
                }}
              >
                Rozpocznij dwa ślepe przebiegi wybranych plansz
              </button>
            </>
          ) : null}
          {readiness ? <GridContentReadiness value={readiness} /> : null}
          {mode === 'ordinary' && chosen && cohort.manifestSha256 ? (
            <GridContentOrdinary
              key={`${cohort.id}:${cohort.manifestSha256}:${chosen.source.sourceId}:${chosen.positionIndex}`}
              api={api}
              apiBaseUrl={apiBaseUrl}
              gameId={gameId}
              cohortId={cohort.id}
              manifestSha256={cohort.manifestSha256}
              target={chosen}
            />
          ) : null}
          <details>
            <summary>Identyfikatory zestawu</summary>
            <p>
              {cohort.id} · {cohort.manifestSha256}
            </p>
          </details>
        </>
      ) : null}
    </section>
  );
}
