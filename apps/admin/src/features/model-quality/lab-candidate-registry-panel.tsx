'use client';

import type {
  LabSymbolCandidateResponse,
  SymbolModelActivationPreviewResponse,
  SymbolModelIterationResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  clearLabRegistryCommand,
  readPendingLabRegistryCommand,
  reconcileLabRegistryFailure,
  saveLabRegistryCommand,
  type PendingLabRegistryCommand,
} from './lab-registry-command';

export function LabCandidateRegistryPanel({
  apiBaseUrl,
  gameId,
  activeIterationId,
  iterations,
  onChanged,
}: {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly activeIterationId: string | null;
  readonly iterations: readonly SymbolModelIterationResponse[];
  readonly onChanged: () => Promise<void>;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [candidates, setCandidates] = useState<
    readonly LabSymbolCandidateResponse[]
  >([]);
  const [preview, setPreview] = useState<LabSymbolCandidateResponse | null>(
    null,
  );
  const [deactivation, setDeactivation] =
    useState<SymbolModelActivationPreviewResponse | null>(null);
  const [pending, setPending] = useState<PendingLabRegistryCommand | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    void api
      .listLabSymbolCandidates(gameId, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.data !== undefined) setCandidates(result.data);
        else
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać modeli pilota.',
            ),
          );
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Nie udało się pobrać modeli pilota.');
      });
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setPreview(null);
      setDeactivation(null);
      setCandidates([]);
      try {
        setPending(readPendingLabRegistryCommand(localStorage, gameId));
      } catch {
        setError('Nie można odczytać zapisanej operacji modelu.');
      }
    });
    return () => controller.abort();
  }, [api, gameId]);

  async function prepareImport(fingerprint: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await api.previewLabSymbolCandidateImport(
        gameId,
        fingerprint,
      );
      if (result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Podgląd modelu jest niedostępny.'),
        );
      } else {
        setPreview(result.data);
        setDeactivation(null);
      }
    } catch {
      setError('Połączenie zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  async function prepareDeactivation() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await api.previewSymbolModelDeactivation(gameId);
      if (result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Podgląd wyłączenia jest niedostępny.'),
        );
      } else {
        setDeactivation(result.data);
        setPreview(null);
      }
    } catch {
      setError('Połączenie zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  async function execute(command: PendingLabRegistryCommand) {
    if (busy || command.gameId !== gameId) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      // Persist the complete canonical command before sending it. Recovery
      // reuses both its operation ID and old expected-current revision.
      const frozen = saveLabRegistryCommand(localStorage, command);
      setPending(frozen);
      const result =
        frozen.kind === 'import'
          ? await api.importLabSymbolCandidate(gameId, frozen.body)
          : await api.deactivateSymbolModel(gameId, frozen.body);
      if (result.data === undefined) {
        if (
          reconcileLabRegistryFailure(
            localStorage,
            gameId,
            result.response?.status ?? 0,
          )
        ) {
          setPending(null);
          setPreview(null);
          setDeactivation(null);
          await onChanged();
        }
        setError(
          apiErrorMessage(
            result.error,
            'Operacja nie została potwierdzona. Możesz ją ponowić.',
          ),
        );
        return;
      }
      clearLabRegistryCommand(localStorage, gameId);
      setPending(null);
      setPreview(null);
      setDeactivation(null);
      setNotice(
        frozen.kind === 'import'
          ? 'Zlecono sprawdzenie modelu. Postęp znajdziesz w zakładce Joby. Aktywacja wymaga osobnego potwierdzenia.'
          : 'Rozpoznawanie nowych zdjęć jest wyłączone. Zapisane korekty pozostają dostępne.',
      );
      await onChanged();
    } catch {
      setError(
        'Nie otrzymano potwierdzenia operacji. Ponów zapisaną operację.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="modelQualityPanel" aria-labelledby="lab-registry-title">
      <h3 id="lab-registry-title">Model pilota Mumii</h3>
      <p>Przygotowany model wymaga sprawdzenia i osobnej aktywacji.</p>
      {candidates.length === 0 ? (
        <p className="mutedText">Brak przygotowanych modeli tej gry.</p>
      ) : (
        <ul>
          {candidates.map((candidate) => {
            const imported = iterations.find(
              (item) =>
                item.originFingerprint === candidate.candidateFingerprint,
            );
            return (
              <li key={candidate.candidateFingerprint}>
                <span>
                  Pilot Mumii{' '}
                  {imported
                    ? `· iteracja #${imported.iterationNumber}: ${imported.status}`
                    : ''}
                </span>{' '}
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={busy || pending !== null || imported !== undefined}
                  onClick={() =>
                    void prepareImport(candidate.candidateFingerprint)
                  }
                >
                  Sprawdź model
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {preview !== null ? (
        <section
          className="modelQualityConfirmation"
          aria-label="Podgląd importu modelu"
        >
          <h4>Pilot, nie wynik dla wszystkich zdjęć</h4>
          <p>
            34 z 34 poprawnych wyników na wybranych przez człowieka zdjęciach
            kontrolnych. Nie określa to trafności na całym zbiorze.
          </p>
          <p>
            Dane rozwojowe: {preview.summary.developmentOrigins.human} oznaczeń
            człowieka, {preview.summary.developmentOrigins.ai_visual_assessment}{' '}
            ocen AI. Import nie tworzy nowych zatwierdzeń człowieka.
          </p>
          <button
            type="button"
            className="primaryButton"
            disabled={busy || pending !== null}
            onClick={() =>
              void execute({
                kind: 'import',
                gameId,
                body: {
                  candidateFingerprint: preview.candidateFingerprint,
                  idempotencyKey: crypto.randomUUID(),
                },
              })
            }
          >
            Potwierdź sprawdzenie i import
          </button>{' '}
          <button
            type="button"
            className="secondaryButton"
            disabled={busy}
            onClick={() => setPreview(null)}
          >
            Anuluj
          </button>
        </section>
      ) : null}
      <button
        type="button"
        className="secondaryButton"
        disabled={busy || activeIterationId === null || pending !== null}
        onClick={() => void prepareDeactivation()}
      >
        Wyłącz rozpoznawanie
      </button>
      {deactivation?.currentModelIterationId ? (
        <section
          className="modelQualityConfirmation"
          aria-label="Potwierdzenie wyłączenia modelu"
        >
          <p>
            Nowe zdjęcia będą wymagać ponownej aktywacji modelu. Rozpoczęte
            zadania zachowają swój model.
          </p>
          <button
            type="button"
            className="primaryButton"
            disabled={busy || pending !== null}
            onClick={() => {
              if (deactivation.currentModelIterationId === null) return;
              void execute({
                kind: 'deactivate',
                gameId,
                body: {
                  expectedCurrentModelIterationId:
                    deactivation.currentModelIterationId,
                  actor: 'local-owner',
                  reason: 'Owner-confirmed model deactivation.',
                  idempotencyKey: crypto.randomUUID(),
                },
              });
            }}
          >
            Potwierdź wyłączenie
          </button>{' '}
          <button
            type="button"
            className="secondaryButton"
            disabled={busy}
            onClick={() => setDeactivation(null)}
          >
            Anuluj
          </button>
        </section>
      ) : null}
      {pending !== null ? (
        <button
          type="button"
          className="primaryButton"
          disabled={busy}
          onClick={() => void execute(pending)}
        >
          Ponów zapisaną operację
        </button>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {error ? (
        <p role="alert" className="modelQualityError">
          {error}
        </p>
      ) : null}
    </section>
  );
}
