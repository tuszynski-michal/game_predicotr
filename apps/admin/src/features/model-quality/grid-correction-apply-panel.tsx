'use client';

import type {
  AdminApiClient,
  GameResponse,
  GridCorrectionApplyPreview,
  GridCorrectionApplyView,
  GridCorrectionApplyStartCommand,
  GridCorrectionLearningView,
  GridModelVersionResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  archiveLearningCommand,
  learningActive,
  learningStatus,
} from './grid-correction-learning-state';
import {
  answeredRefusal,
  gameName,
  reasonLabel,
  shortDate,
  versionName,
} from './grid-model-state';

type Client = Pick<
  AdminApiClient,
  | 'previewGridCorrectionApply'
  | 'startGridCorrectionApply'
  | 'listGridCorrectionApply'
  | 'getGridCorrectionApply'
  | 'resumeGridCorrectionApply'
>;
type Command =
  | {
      readonly kind: 'apply';
      readonly key: string;
      readonly body: GridCorrectionApplyStartCommand;
    }
  | { readonly kind: 'resume'; readonly key: string; readonly target: string };
interface Props {
  readonly api: Client;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly learning: GridCorrectionLearningView;
  readonly games: readonly GameResponse[];
  readonly versions: readonly GridModelVersionResponse[];
  readonly onChanged: () => void;
}

export function GridCorrectionApplyPanel(props: Props) {
  return (
    <Apply
      key={`${props.apiBaseUrl}:${props.gameId}:${props.learning.learningId}`}
      {...props}
    />
  );
}

function readCommand(key: string): Command | null {
  const raw = window.localStorage.getItem(key);
  if (raw === null) return null;
  const value: unknown = JSON.parse(raw);
  if (
    !value ||
    typeof value !== 'object' ||
    !('kind' in value) ||
    !('key' in value) ||
    typeof value.key !== 'string' ||
    (value.kind !== 'apply' && value.kind !== 'resume') ||
    (value.kind === 'resume' &&
      (!('target' in value) || typeof value.target !== 'string')) ||
    (value.kind === 'apply' &&
      (!('body' in value) ||
        !value.body ||
        typeof value.body !== 'object' ||
        !('idempotencyKey' in value.body) ||
        value.body.idempotencyKey !== value.key))
  )
    throw new Error(
      'Zapisane polecenie zastosowania jest nieczytelne. Zachowaj je przed ponowieniem.',
    );
  return value as Command;
}

function Apply({
  api,
  apiBaseUrl,
  gameId,
  learning,
  games,
  versions,
  onChanged,
}: Props) {
  const storageKey = `game-predictor:grid-correction-apply:${apiBaseUrl}:${gameId}:${learning.learningId}`;
  const [preview, setPreview] = useState<GridCorrectionApplyPreview | null>(
    null,
  );
  const [operations, setOperations] = useState<
    readonly GridCorrectionApplyView[]
  >([]);
  const [additional, setAdditional] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState<Command | null>(null);
  const [corrupt, setCorrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(0),
    mounted = useRef(true),
    locked = useRef(false);
  const operationsRequest = useRef(0);
  const activeOperations = useRef(new Set<string>());
  const scope = useMemo(() => [...additional].sort(), [additional]);

  async function readPreview(selected: readonly string[]) {
    const token = ++request.current;
    setPreview(null);
    setConfirmed(false);
    const result = await api
      .previewGridCorrectionApply(gameId, learning.learningId, [...selected])
      .catch((failure) => {
        if (token !== request.current || !mounted.current) return null;
        throw failure;
      });
    if (token !== request.current || !mounted.current) return;
    if (!result) return;
    if (
      !result.data ||
      result.data.gameId !== gameId ||
      result.data.learningId !== learning.learningId
    )
      throw new Error(
        apiErrorMessage(
          result.error,
          'Nie udało się odczytać podglądu zastosowania.',
        ),
      );
    setPreview(result.data);
    setError('');
  }
  async function readOperations() {
    const token = ++operationsRequest.current;
    const result = await api.listGridCorrectionApply(
      gameId,
      learning.learningId,
    );
    if (!mounted.current || token !== operationsRequest.current) return;
    if (!result.data)
      throw new Error('Nie udało się odczytać historii zastosowania.');
    const completed = result.data.items.some(
      (item) =>
        item.status === 'completed' &&
        activeOperations.current.has(item.applyId),
    );
    activeOperations.current = new Set(
      result.data.items
        .filter((item) => learningActive(item.status))
        .map((item) => item.applyId),
    );
    setOperations(result.data.items);
    if (completed) onChanged();
  }
  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => {
      if (!mounted.current) return;
      try {
        setPending(readCommand(storageKey));
      } catch (failure) {
        setCorrupt(true);
        setError(String(failure));
      }
      void readOperations().catch((failure) => {
        if (mounted.current) setError(String(failure));
      });
    });
    return () => {
      mounted.current = false;
      request.current += 1;
      operationsRequest.current += 1;
    };
    // The component is keyed by API, game and learning ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, gameId, learning.learningId, storageKey]);
  useEffect(() => {
    queueMicrotask(() => {
      if (!mounted.current) return;
      void readPreview(scope).catch((failure) => {
        if (mounted.current) setError(String(failure));
      });
    });
    // All preview requests are GET. A scope change invalidates the previous read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);
  const active = operations.some((item) => learningActive(item.status));
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(
      () => void readOperations().catch((failure) => setError(String(failure))),
      15_000,
    );
    return () => window.clearInterval(timer);
    // GET-only polling while an apply operation is active.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  async function send(command: Command) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError('');
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(command));
      setPending(command);
      const result =
        command.kind === 'apply'
          ? await api.startGridCorrectionApply(
              gameId,
              learning.learningId,
              command.body,
            )
          : await api.resumeGridCorrectionApply(
              gameId,
              learning.learningId,
              command.target,
            );
      if (!mounted.current) return;
      if (result.data || answeredRefusal(result)) {
        if (readCommand(storageKey)?.key === command.key)
          window.localStorage.removeItem(storageKey);
        setPending(null);
      }
      if (!result.data) {
        if (answeredRefusal(result)) await readPreview(scope);
        throw new Error(
          apiErrorMessage(
            result.error,
            answeredRefusal(result)
              ? 'Polecenie odrzucone. Sprawdź aktualny podgląd i potwierdź ponownie.'
              : 'Odpowiedź niepotwierdzona. Ponów zapisane polecenie zastosowania.',
          ),
        );
      }
      operationsRequest.current += 1;
      if (learningActive(result.data.status))
        activeOperations.current.add(result.data.applyId);
      setOperations((current) => [
        result.data,
        ...current.filter((item) => item.applyId !== result.data.applyId),
      ]);
      setConfirmed(false);
      onChanged();
    } catch (failure) {
      if (mounted.current) setError(String(failure));
    } finally {
      locked.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const disabled = busy || pending !== null || corrupt;
  const alreadyDefault =
    preview?.blockers.includes('GRID_APPLY_ALREADY_DEFAULT') ?? false;
  const STEP_LABELS: Readonly<Record<string, string>> = {
    publish: 'Publikacja',
    set_default: 'Wersja domyślna',
    comparison: 'Kontrola przypisanej wersji',
    activate: 'Przypisanie gry',
  };
  return (
    <section aria-label="Zastosowanie wersji">
      <h4>Zastosuj wersję</h4>
      <p>
        Domyślnie: wspólny model dla nowych gier i bieżąca gra. Starsze importy
        zachowają swoje wersje i ręczne korekty.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {corrupt ? (
        <p role="alert">
          Nieczytelne polecenie zastosowania blokuje nowe zmiany. Zachowaj je
          przed odłożeniem.
        </p>
      ) : null}
      {pending ? (
        <aside>
          <p>
            Odpowiedź niepotwierdzona. Zachowano dokładne polecenie
            zastosowania.
          </p>
          <button
            className="secondaryButton"
            type="button"
            disabled={busy}
            onClick={() => void send(pending)}
          >
            Ponów zapisane polecenie zastosowania
          </button>
        </aside>
      ) : null}
      {pending || corrupt ? (
        <button
          className="secondaryButton"
          type="button"
          disabled={busy}
          onClick={() => {
            try {
              archiveLearningCommand(window.localStorage, storageKey);
              setPending(null);
              setCorrupt(false);
              setError('');
            } catch (failure) {
              setError(String(failure));
            }
          }}
        >
          Zachowaj i odłóż zastosowanie
        </button>
      ) : null}
      <button
        className="secondaryButton"
        type="button"
        disabled={busy}
        onClick={() =>
          void Promise.all([readPreview(scope), readOperations()]).catch(
            (failure) => setError(String(failure)),
          )
        }
      >
        Odśwież podgląd zastosowania
      </button>
      {preview ? (
        <>
          <p>
            Kandydat:{' '}
            {preview.versionLabel ?? versionName(versions, preview.versionId)}.
            Obecny wspólny model:{' '}
            {versionName(versions, preview.defaultVersionId)}.
          </p>
          <ul aria-label="Gry otrzymujące wersję">
            {preview.targets.map((target) => (
              <li key={target.gameId}>
                {gameName(games, target.gameId)} · aktualnie{' '}
                {versionName(versions, target.assignedVersionId)}
                {target.requiresComparison
                  ? ' · wymaga kontroli względem przypisanej wersji'
                  : ''}
              </li>
            ))}
          </ul>
          {!alreadyDefault ? (
            <details>
              <summary>Zastosuj także w innych ocenionych grach</summary>
              <p>
                Każda dodatkowa gra wymaga jawnego wyboru i aktualnej oceny.
              </p>
              {learning.requiredGameIds
                .filter(
                  (id) =>
                    id !== gameId && !preview.excludedGameIds.includes(id),
                )
                .map((id) => (
                  <label key={id}>
                    <input
                      type="checkbox"
                      disabled={disabled || active}
                      checked={additional.includes(id)}
                      onChange={(event) =>
                        setAdditional((current) =>
                          event.target.checked
                            ? [...current, id]
                            : current.filter((value) => value !== id),
                        )
                      }
                    />
                    {gameName(games, id)}
                  </label>
                ))}
            </details>
          ) : null}
          <p>
            Ograniczenie dowodu: zdjęcia nie potwierdzają niezależności sesji
            ani nieznanego wcześniejszego użycia danych.
          </p>
          <ul>
            {preview.limitations.map((code) => (
              <li key={code}>{reasonLabel(code)}</li>
            ))}
          </ul>
          {preview.excludedGameIds.length ? (
            <p>
              Bez zmiany przypisania:{' '}
              {preview.excludedGameIds
                .map((id) => gameName(games, id))
                .join(', ')}
              .
            </p>
          ) : null}
          {preview.blockers.length ? (
            <ul aria-label="Blokady zastosowania">
              {preview.blockers.map((code) => (
                <li key={code}>{reasonLabel(code)}</li>
              ))}
            </ul>
          ) : null}
          {!alreadyDefault ? (
            <>
              <label>
                <input
                  type="checkbox"
                  disabled={disabled || active}
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                Potwierdzam ograniczony dowód oparty na zdjęciach i zakres
                zastosowania
              </label>
              <button
                className="primaryButton"
                type="button"
                disabled={disabled || active || !confirmed || !preview.canApply}
                onClick={() => {
                  const key = crypto.randomUUID();
                  void send({
                    kind: 'apply',
                    key,
                    body: {
                      idempotencyKey: key,
                      previewSha256: preview.previewSha256,
                      additionalGameIds: scope,
                      confirmLimitedEvidence: true,
                    },
                  });
                }}
              >
                Zastosuj wersję
              </button>
            </>
          ) : null}
        </>
      ) : (
        <p aria-busy={!error}>
          {error
            ? 'Podgląd zastosowania niedostępny.'
            : 'Sprawdzanie możliwości zastosowania…'}
        </p>
      )}
      <h4>Historia zastosowania</h4>
      {!operations.length ? (
        <p>Nie zastosowano jeszcze tego kandydata.</p>
      ) : null}
      {operations.map((operation) => (
        <article key={operation.applyId} aria-label="Przebieg zastosowania">
          <p>
            {shortDate(operation.createdAt)} ·{' '}
            {learningStatus[operation.status]}
            {operation.errorCode
              ? ` · ${reasonLabel(operation.errorCode)}`
              : ''}
          </p>
          <ol>
            {operation.steps.map((step, index) => (
              <li key={index}>
                {STEP_LABELS[step.kind]}
                {step.gameId ? ` · ${gameName(games, step.gameId)}` : ''}:{' '}
                {step.status === 'completed'
                  ? step.receipt?.kind === 'already-published'
                    ? 'Potwierdzono istniejącą publikację'
                    : 'Potwierdzono'
                  : step.status === 'waiting'
                    ? 'Oczekiwanie'
                    : 'Do wykonania'}
              </li>
            ))}
          </ol>
          {operation.steps.some((step) => step.status === 'completed') &&
          operation.status !== 'completed' ? (
            <p>
              Wykonane kroki są zachowane. Wznowienie kontynuuje ten sam
              przebieg.
            </p>
          ) : null}
          {['failed', 'cancelled'].includes(operation.status) ? (
            <button
              className="primaryButton"
              type="button"
              disabled={disabled}
              onClick={() =>
                void send({
                  kind: 'resume',
                  key: crypto.randomUUID(),
                  target: operation.applyId,
                })
              }
            >
              Wznów zastosowanie
            </button>
          ) : null}
        </article>
      ))}
    </section>
  );
}
