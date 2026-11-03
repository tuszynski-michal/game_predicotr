'use client';

import type {
  AdminApiClient,
  SourceReplacementWorkingResponse,
  SourceReplacementRestoreCommand,
  OperationalImageReviewItemResponse,
  OperationalImageReviewResolutionCommand,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '../../api/admin-api-client';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import { DeferredBoardCellGeometryEditor } from '../../../../reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor';
import { OperationalReviewGeometryEditor } from '../../../../reviewer/src/features/operational-reviews/operational-review-geometry-editor';
import { GeometryCorrectionHistory } from '../../../../reviewer/src/features/operational-reviews/geometry-correction-history';
import { RejectBoardControl } from '../../../../reviewer/src/features/operational-reviews/reject-board-control';
import {
  rejectDeferredSlot,
  rejectReviewItem,
} from '../../../../reviewer/src/features/operational-reviews/board-rejection-actions';
import {
  buildOperationalReviewResolutionCommand,
  operationalReviewAssetUrl,
} from '../../../../reviewer/src/features/operational-reviews/operational-review-state';

// Commands remain durable until the same server receipt has been received.
function restoreCommand(
  value: unknown,
  batchId: string,
  entryId: string,
): value is SourceReplacementRestoreCommand {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return (
    item.batchId === batchId &&
    item.entryId === entryId &&
    item.confirmed === true &&
    typeof item.actor === 'string' &&
    typeof item.idempotencyKey === 'string' &&
    Number.isInteger(item.expectedRevision) &&
    Array.isArray(item.readability) &&
    item.readability.every(
      (cell) =>
        cell &&
        typeof cell === 'object' &&
        typeof cell.cellId === 'string' &&
        typeof cell.identity === 'string' &&
        Number.isInteger(cell.revision) &&
        cell.readable === true,
    )
  );
}

export function SourceReplacementWorking({
  apiBaseUrl,
  gameId,
  batchId,
  entryId,
  client,
}: {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly batchId: string;
  readonly entryId: string;
  readonly client?: AdminApiClient;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [client, apiBaseUrl],
  );
  const [view, setView] = useState<SourceReplacementWorkingResponse | null>(
    null,
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [loaded, setLoaded] = useState<string[]>([]);
  const [pending, setPending] =
    useState<SourceReplacementRestoreCommand | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [recoveryReady, setRecoveryReady] = useState(false);
  const request = useRef(0);
  const storageKey = `replacement-restore:${gameId}:${batchId}:${entryId}`;
  const load = useCallback(async () => {
    const ticket = ++request.current;
    setBusy(true);
    setError('');
    setChecked([]);
    setLoaded([]);
    try {
      const result = await api.getSourceReplacementWorking(
        gameId,
        batchId,
        entryId,
      );
      if (ticket !== request.current) return;
      if (!result.data)
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie udało się odczytać nowych plansz.',
          ),
        );
      setView(result.data);
      setRefresh((value) => value + 1);
    } catch (cause) {
      if (ticket === request.current)
        setError(
          `${cause instanceof Error ? cause.message : 'Przerwano połączenie.'} Odśwież stan wymiany.`,
        );
    } finally {
      if (ticket === request.current) setBusy(false);
    }
  }, [api, gameId, batchId, entryId]);
  useEffect(() => {
    let active = true;
    const generation = request;
    queueMicrotask(() => {
      if (active) void load();
    });
    return () => {
      active = false;
      generation.current++;
    };
  }, [load]);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const raw = localStorage.getItem(storageKey);
        if (raw) {
          const value: unknown = JSON.parse(raw);
          if (!restoreCommand(value, batchId, entryId)) throw new Error();
          setPending(value);
        }
        setRecoveryReady(true);
      } catch {
        setError(
          'Nie można odtworzyć potwierdzenia. Sprawdź dostępność pamięci przeglądarki i odśwież stronę.',
        );
      }
    });
    return () => {
      active = false;
    };
  }, [storageKey, batchId, entryId]);
  async function restore() {
    if (!view || !recoveryReady) return;
    setBusy(true);
    setError('');
    try {
      const command = pending ?? {
        batchId,
        entryId,
        expectedRevision: view.revision,
        idempotencyKey: crypto.randomUUID(),
        confirmed: true as const,
        actor: 'local-admin',
        readability: view.readability.map((cell) => ({
          cellId: cell.cellId,
          identity: cell.identity,
          revision: cell.revision,
          readable: true as const,
        })),
      };
      localStorage.setItem(storageKey, JSON.stringify(command));
      setPending(command);
      const result = await api.restoreSourceReplacementEntry(gameId, command);
      if (!result.data) {
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(storageKey);
          setPending(null);
        }
        throw new Error(
          apiErrorMessage(result.error, 'Nie udało się potwierdzić wymiany.'),
        );
      }
      localStorage.removeItem(storageKey);
      setPending(null);
      await load();
    } catch (cause) {
      setError(
        `${cause instanceof Error ? cause.message : 'Brak odpowiedzi serwera.'} Odśwież stan lub ponów zapisane potwierdzenie.`,
      );
    } finally {
      setBusy(false);
    }
  }
  const slot = view?.slots.find((item) => item.sequenceNumber === selected);
  const importJobId = view?.importJobId;
  const scope = useMemo(
    () => (importJobId ? { gameId, importJobId } : null),
    [gameId, importJobId],
  );
  return (
    <section aria-label="Nowe zdjęcie i sprawdzenie wymiany">
      <button type="button" disabled={busy} onClick={() => void load()}>
        Odśwież nowe plansze
      </button>
      {busy && <p role="status">Odczyt lub zapis stanu wymiany…</p>}
      {error && <p role="alert">{error}</p>}
      {view?.phase === 'restored' ? (
        <p role="status">
          Wymiana potwierdzona na serwerze. Nowe plansze są źródłem bieżącym.
        </p>
      ) : (
        <>
          {view?.importJobId && !view.readyToRestore && (
            <p>
              Sprawdź wszystkie plansze tego samego nowego zdjęcia. Korektę i
              cofnięcie odrzucenia wykonasz poniżej. Luka pozostaje otwarta do
              końcowego potwierdzenia.
            </p>
          )}
          {view && !view.importJobId && (
            <p>
              Nie rozpoczęto jeszcze importu zamiennika. Otwórz gotowe
              zamienniki w imporcie plansz.
            </p>
          )}
          {view?.importJobId && !view.slots.length && (
            <p>
              Import jeszcze przygotowuje zdjęcie. Po zakończeniu odśwież nowe
              plansze.
            </p>
          )}
          {view?.slots.map((item) => (
            <button
              type="button"
              key={item.sequenceNumber}
              disabled={busy || !!pending}
              onClick={() => setSelected(item.sequenceNumber)}
            >
              Plansza {item.sequenceNumber} —{' '}
              {item.canonical
                ? 'zatwierdzona'
                : item.status === 'rejected'
                  ? 'odrzucona, dostępne cofnięcie'
                  : 'wymaga sprawdzenia'}
            </button>
          ))}
          {slot && scope && (
            <div key={`${slot.sequenceNumber}:${refresh}`}>
              <h5>Plansza {slot.sequenceNumber}</h5>
              {slot.pendingGeometryId &&
                !slot.reviewItemId &&
                slot.status !== 'rejected' && (
                  <RejectBoardControl
                    subject={`plansza ${slot.sequenceNumber}`}
                    consequences={[
                      'Plansza przestanie czekać na korektę. Wymiana pozostanie otwarta. Odrzucenie można cofnąć w ostatnich korektach.',
                    ]}
                    onDone={async () => {
                      await load();
                    }}
                    onRefused={async (message) => setError(message)}
                    submit={async (command) => {
                      const current = await api.getPendingBoardCellGeometry(
                        slot.pendingGeometryId!,
                        scope,
                      );
                      if (!current.data)
                        return {
                          kind: 'refused' as const,
                          code: null,
                          message:
                            'Nie udało się odczytać planszy. Odśwież widok.',
                        };
                      return rejectDeferredSlot(
                        api,
                        scope,
                        {
                          pendingGeometryId: slot.pendingGeometryId!,
                          expectedGeometryRevision:
                            current.data.expectedGeometryRevision,
                        },
                        command,
                      );
                    }}
                  />
                )}
              {slot.pendingGeometryId &&
                !slot.reviewItemId &&
                slot.status !== 'rejected' && (
                  <DeferredBoardCellGeometryEditor
                    api={api}
                    apiBaseUrl={apiBaseUrl}
                    itemId={slot.pendingGeometryId}
                    scope={scope}
                    onConflict={async (message) => setError(message)}
                    onMaterialized={async () => {
                      await load();
                    }}
                  />
                )}
              {slot.reviewItemId && (
                <ReplacementReview
                  key={slot.reviewItemId}
                  api={api}
                  apiBaseUrl={apiBaseUrl}
                  scope={scope}
                  reviewItemId={slot.reviewItemId}
                  sequenceNumber={slot.sequenceNumber}
                  onSaved={load}
                />
              )}
            </div>
          )}
          {scope && (
            <GeometryCorrectionHistory
              api={api}
              gameId={gameId}
              importJobId={scope.importJobId}
              onReverted={load}
              refreshToken={refresh}
            />
          )}
          {view?.readyToRestore && scope && (
            <fieldset disabled={busy || !!pending}>
              <legend>Oceń czytelność nowych pól</legend>
              <p>
                Każda plansza jest zatwierdzona. Sprawdź poniższe nowe wycinki i
                zaznacz, że symbole są czytelne.
              </p>
              {view.readability.map((cell) => (
                <label
                  key={`${cell.identity}:${refresh}`}
                  style={{ display: 'inline-block', padding: 12 }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    alt={`Nowy wycinek: plansza ${cell.sequenceNumber}, pole ${cell.cellIndex + 1}`}
                    width={120}
                    height={120}
                    src={operationalReviewAssetUrl(
                      apiBaseUrl,
                      scope,
                      cell.reviewItemId,
                      'cell',
                      { cellIndex: cell.cellIndex, version: cell.identity },
                    )}
                    onLoad={() =>
                      setLoaded((current) =>
                        current.includes(cell.identity)
                          ? current
                          : [...current, cell.identity],
                      )
                    }
                    onError={() => {
                      setLoaded((current) =>
                        current.filter((id) => id !== cell.identity),
                      );
                      setError(
                        'Nie udało się wczytać nowego wycinka. Odśwież widok.',
                      );
                    }}
                  />
                  <span>
                    Plansza {cell.sequenceNumber}, pole {cell.cellIndex + 1}
                  </span>
                  <input
                    type="checkbox"
                    disabled={!loaded.includes(cell.identity)}
                    checked={checked.includes(cell.identity)}
                    onChange={(event) =>
                      setChecked((current) =>
                        event.target.checked
                          ? [...current, cell.identity]
                          : current.filter((id) => id !== cell.identity),
                      )
                    }
                  />
                  Symbol jest czytelny
                </label>
              ))}
            </fieldset>
          )}
          {(view?.readyToRestore || pending) && (
            <button
              type="button"
              disabled={
                busy ||
                !recoveryReady ||
                (!pending &&
                  (!view?.readability.length ||
                    view.readability.some(
                      (cell) =>
                        !checked.includes(cell.identity) ||
                        !loaded.includes(cell.identity),
                    )))
              }
              onClick={() => void restore()}
            >
              {pending
                ? 'Ponów zapisane potwierdzenie'
                : 'Potwierdź czytelność i zakończ wymianę'}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function ReplacementReview({
  api,
  apiBaseUrl,
  scope,
  reviewItemId,
  sequenceNumber,
  onSaved,
}: {
  readonly api: AdminApiClient;
  readonly apiBaseUrl: string;
  readonly scope: { gameId: string; importJobId: string };
  readonly reviewItemId: string;
  readonly sequenceNumber: number;
  readonly onSaved: () => Promise<void>;
}) {
  const [item, setItem] = useState<OperationalImageReviewItemResponse | null>(
    null,
  );
  const [symbols, setSymbols] = useState<SymbolResponse[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [visibleCells, setVisibleCells] = useState<number[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] =
    useState<OperationalImageReviewResolutionCommand | null>(null);
  const [recoveryReady, setRecoveryReady] = useState(false);
  const key = `replacement-review:${scope.gameId}:${reviewItemId}`;
  useEffect(() => {
    let active = true;
    void Promise.all([
      api.getOperationalImageReviewItem(reviewItemId, scope),
      api.listSymbols(scope.gameId),
    ])
      .then(([review, catalog]) => {
        if (!active) return;
        if (!review.data || !catalog.data) {
          setError(
            'Nie udało się wczytać planszy i symboli. Odśwież nowe plansze.',
          );
          return;
        }
        setItem(review.data);
        setCodes(review.data.cells.map((cell) => cell.currentSymbolCode));
        setSymbols(catalog.data);
        try {
          const saved = localStorage.getItem(key);
          if (saved) {
            const command = JSON.parse(
              saved,
            ) as OperationalImageReviewResolutionCommand;
            if (
              command.sequenceNumber !== sequenceNumber ||
              !command.idempotencyKey ||
              !Array.isArray(command.cells)
            )
              throw new Error();
            setPending(command);
          }
          setRecoveryReady(true);
        } catch {
          setError(
            'Nie można odtworzyć zapisu planszy. Odśwież stronę i sprawdź pamięć przeglądarki.',
          );
        }
      })
      .catch(() => {
        if (active) setError('Przerwano odczyt planszy. Odśwież nowe plansze.');
      });
    return () => {
      active = false;
    };
  }, [api, reviewItemId, scope, key, sequenceNumber]);
  async function save() {
    if (!item || !recoveryReady) return;
    setBusy(true);
    setError('');
    try {
      const command =
        pending ??
        buildOperationalReviewResolutionCommand(
          item,
          sequenceNumber,
          codes,
          crypto.randomUUID(),
        );
      localStorage.setItem(key, JSON.stringify(command));
      setPending(command);
      const result = await api.resolveOperationalImageReviewItem(
        reviewItemId,
        scope,
        command,
      );
      if (!result.data) {
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(key);
          setPending(null);
        }
        throw new Error(
          apiErrorMessage(result.error, 'Nie udało się zatwierdzić planszy.'),
        );
      }
      localStorage.removeItem(key);
      setPending(null);
      await onSaved();
    } catch (cause) {
      setError(
        `${cause instanceof Error ? cause.message : 'Brak odpowiedzi.'} Odśwież planszę lub ponów zapisane zatwierdzenie.`,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={`Sprawdzenie symboli planszy ${sequenceNumber}`}>
      {error && <p role="alert">{error}</p>}
      {!item && !error && <p role="status">Wczytywanie nowych symboli…</p>}
      {item?.status === 'rejected' && (
        <p>
          Plansza odrzucona. Cofnij odrzucenie w ostatnich korektach, aby
          ponownie ją poprawić.
        </p>
      )}
      {item && item.status !== 'rejected' && (
        <>
          <RejectBoardControl
            subject={`plansza ${sequenceNumber}`}
            disabled={
              busy ||
              !!pending ||
              item.status === 'accepted' ||
              item.status === 'corrected'
            }
            consequences={[
              'Wymiana pozostanie otwarta. Odrzucenie można cofnąć w ostatnich korektach.',
            ]}
            onDone={async () => {
              await onSaved();
            }}
            onRefused={async (message) => setError(message)}
            submit={(command) =>
              rejectReviewItem(
                api,
                scope,
                {
                  reviewItemId: item.id,
                  geometryRevision: item.geometryRevision,
                  resolutionRevision: item.resolutionRevision,
                },
                command,
              )
            }
          />
          <OperationalReviewGeometryEditor
            api={api}
            apiBaseUrl={apiBaseUrl}
            importJobId={scope.importJobId}
            item={item}
            onSaved={() => void onSaved()}
          />
          <fieldset disabled={busy || !!pending}>
            <legend>Sprawdź wszystkie 15 symboli</legend>
            {item.cells.map((cell, index) => (
              <label
                key={cell.cellIndex}
                style={{ display: 'inline-block', padding: 8 }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt={`Nowe pole ${cell.cellIndex + 1}`}
                  width={96}
                  height={96}
                  src={operationalReviewAssetUrl(
                    apiBaseUrl,
                    scope,
                    item.id,
                    'cell',
                    {
                      cellIndex: cell.cellIndex,
                      version: cell.cropChecksumSha256,
                    },
                  )}
                  onLoad={() =>
                    setVisibleCells((current) =>
                      current.includes(cell.cellIndex)
                        ? current
                        : [...current, cell.cellIndex],
                    )
                  }
                  onError={() => {
                    setVisibleCells((current) =>
                      current.filter((index) => index !== cell.cellIndex),
                    );
                    setError(
                      'Nie udało się wczytać wycinka. Odśwież nowe plansze przed zatwierdzeniem.',
                    );
                  }}
                />
                <select
                  aria-label={`Symbol pola ${cell.cellIndex + 1}`}
                  value={codes[index]}
                  onChange={(event) =>
                    setCodes((current) =>
                      current.map((code, position) =>
                        position === index ? event.target.value : code,
                      ),
                    )
                  }
                >
                  {!symbols.some((symbol) => symbol.code === codes[index]) && (
                    <option value={codes[index]}>Wybierz symbol</option>
                  )}
                  {symbols.map((symbol) => (
                    <option key={symbol.id} value={symbol.code}>
                      {symbol.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            disabled={
              busy ||
              !recoveryReady ||
              (!pending &&
                (codes.length !== 15 ||
                  visibleCells.length !== 15 ||
                  codes.some(
                    (code) => !symbols.some((symbol) => symbol.code === code),
                  )))
            }
            onClick={() => void save()}
          >
            {pending
              ? 'Ponów zapisane zatwierdzenie'
              : 'Zatwierdź sprawdzone symbole planszy'}
          </button>
        </>
      )}
    </section>
  );
}
