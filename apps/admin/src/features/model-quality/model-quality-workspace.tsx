'use client';

import type {
  ModelQualityResponse,
  PendingSymbolReinferencePreviewResponse,
  SymbolModelActivationAction,
  SymbolModelActivationPreviewResponse,
  SymbolModelActivationResponse,
  SymbolModelIterationResponse,
  VerifiedTrainingCohortPreviewResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { GridQualityPanel } from '@/features/model-quality/grid-quality-panel';
import {
  freezeModelQualityCohort,
  confirmModelActivation,
  loadModelQuality,
  previewModelActivation,
  previewPendingSymbolReinference as loadPendingSymbolReinference,
  startPendingSymbolReinference,
  type ModelQualityClient,
} from '@/features/model-quality/model-quality-actions';

const OWNER_ACTOR = 'local-owner';

const WARNING_LABELS: Readonly<Record<string, string>> = {
  ACTIVE_HEAVY_JOB_BLOCKS_COHORT_FREEZE:
    'Inna ciężka operacja tej gry jest aktywna. Poczekaj na jej zakończenie.',
  INCOMPLETE_HUMAN_DECISIONS_EXCLUDED:
    'Niekompletne decyzje człowieka zostały wykluczone z danych treningowych.',
  LOW_SOURCE_IMAGE_COVERAGE: 'Dane pochodzą z małej liczby zdjęć źródłowych.',
  LOW_VERIFIED_LAYOUT_COVERAGE:
    'Liczba zweryfikowanych plansz jest mniejsza niż pierwszy próg doradczy.',
  NO_ACTIVE_SYMBOLS: 'Gra nie ma aktywnych symboli.',
};

function warningLabel(code: string): string {
  if (code.startsWith('LOW_SYMBOL_COVERAGE:')) {
    return `Mało przykładów symbolu ${code.slice('LOW_SYMBOL_COVERAGE:'.length)}.`;
  }
  return WARNING_LABELS[code] ?? code;
}

function shortChecksum(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

export function ModelQualityWorkspace({
  apiBaseUrl,
  client,
  gameId,
}: {
  readonly apiBaseUrl: string;
  readonly client?: ModelQualityClient;
  readonly gameId: string;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [quality, setQuality] = useState<ModelQualityResponse | null>(null);
  const [preview, setPreview] =
    useState<VerifiedTrainingCohortPreviewResponse | null>(null);
  const [iterations, setIterations] = useState<
    readonly SymbolModelIterationResponse[]
  >([]);
  const [activations, setActivations] = useState<
    readonly SymbolModelActivationResponse[]
  >([]);
  const [pendingPreview, setPendingPreview] =
    useState<PendingSymbolReinferencePreviewResponse | null>(null);
  const [recalculating, setRecalculating] = useState(false);
  const [activationPreview, setActivationPreview] =
    useState<SymbolModelActivationPreviewResponse | null>(null);
  const [activationAction, setActivationAction] =
    useState<SymbolModelActivationAction>('activate');
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [freezing, setFreezing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const idempotencyKeyRef = useRef<string | null>(null);
  const activationIdempotencyKeyRef = useRef<string | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError('');
      const [result, pendingResult] = await Promise.all([
        loadModelQuality(api, gameId, signal),
        loadPendingSymbolReinference(api, gameId),
      ]);
      if (signal?.aborted) return;
      if (!result.ok) {
        if (result.error !== 'REQUEST_ABORTED') setError(result.error);
        setLoading(false);
        return;
      }
      setQuality(result.quality);
      setPreview(result.preview);
      setIterations(result.iterations);
      setActivations(result.activations);
      if (pendingResult.ok) setPendingPreview(pendingResult.preview);
      setLoading(false);
    },
    [api, gameId],
  );

  useEffect(() => {
    const controller = new AbortController();
    idempotencyKeyRef.current = null;
    queueMicrotask(() => void refresh(controller.signal));
    return () => controller.abort();
  }, [refresh]);

  async function confirmFreeze() {
    if (preview === null || quality === null || freezing || !quality.canFreeze)
      return;
    setFreezing(true);
    setError('');
    setNotice('');
    idempotencyKeyRef.current ??= crypto.randomUUID();
    const result = await freezeModelQualityCohort(api, {
      actor: OWNER_ACTOR,
      gameId,
      idempotencyKey: idempotencyKeyRef.current,
      manifestChecksumSha256: preview.manifestChecksumSha256,
    });
    if (!result.ok) {
      setError(result.error);
      setFreezing(false);
      return;
    }
    setNotice(
      `Uruchomiono trening iteracji #${result.training.iteration.iterationNumber}. ` +
        'Postęp jest widoczny w zakładce Joby.',
    );
    idempotencyKeyRef.current = null;
    setConfirming(false);
    setFreezing(false);
    await refresh();
  }

  async function recalculatePendingSymbols() {
    if (
      pendingPreview === null ||
      pendingPreview.pendingCount === 0 ||
      recalculating
    )
      return;
    setRecalculating(true);
    setError('');
    const result = await startPendingSymbolReinference(api, gameId);
    if (result.ok) {
      setNotice(
        `Uruchomiono przeliczenie oczekujących (job ${result.job.id}).`,
      );
      setPendingPreview({ ...pendingPreview, pendingCount: 0 });
    } else {
      setError(result.error);
    }
    setRecalculating(false);
  }

  async function prepareActivation(
    action: SymbolModelActivationAction,
    iterationId: string,
  ) {
    if (activating) return;
    setError('');
    setNotice('');
    const result = await previewModelActivation(api, {
      action,
      gameId,
      iterationId,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setActivationAction(action);
    setActivationPreview(result.preview);
    activationIdempotencyKeyRef.current = null;
  }

  async function applyActivation() {
    if (activationPreview === null || activating) return;
    setActivating(true);
    setError('');
    setNotice('');
    activationIdempotencyKeyRef.current ??= crypto.randomUUID();
    const result = await confirmModelActivation(api, {
      action: activationAction,
      actor: OWNER_ACTOR,
      gameId,
      idempotencyKey: activationIdempotencyKeyRef.current,
      preview: activationPreview,
    });
    if (!result.ok) {
      setError(result.error);
      setActivating(false);
      return;
    }
    setNotice(
      activationAction === 'rollback'
        ? 'Przywrócono wskazany model. Nowe joby będą przypinane do tej wersji.'
        : 'Aktywowano model. Nowe joby będą przypinane do tej wersji.',
    );
    setActivationPreview(null);
    activationIdempotencyKeyRef.current = null;
    setActivating(false);
    await refresh();
  }

  if (loading && quality === null) {
    return (
      <section className="modelQualityWorkspace">
        <p className="modelQualityLoading">Ładowanie jakości modelu…</p>
      </section>
    );
  }

  if (quality === null || preview === null) {
    return (
      <section className="modelQualityWorkspace">
        <div className="modelQualityError" role="alert">
          <p>{error || 'Brak danych jakości modelu.'}</p>
          <button
            className="secondaryButton"
            onClick={() => void refresh()}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </div>
        <GridQualityPanel apiBaseUrl={apiBaseUrl} gameId={gameId} />
      </section>
    );
  }

  const latestIteration = iterations[0] ?? null;
  const latestActivation = activations[0] ?? null;
  const activeIterationId = latestActivation?.modelIterationId ?? null;
  const rollbackIterationId =
    latestActivation?.previousModelIterationId ?? null;
  const activeIteration =
    iterations.find((iteration) => iteration.id === activeIterationId) ?? null;
  const candidateMetrics = latestIteration?.gateMetrics.candidate;
  const testMetrics =
    candidateMetrics !== null && typeof candidateMetrics === 'object'
      ? (candidateMetrics as Record<string, unknown>).test
      : null;
  const testAccuracy =
    testMetrics !== null && typeof testMetrics === 'object'
      ? (testMetrics as Record<string, unknown>).accuracy
      : null;
  const testMacroRecall =
    testMetrics !== null && typeof testMetrics === 'object'
      ? (testMetrics as Record<string, unknown>).macroRecall
      : null;

  return (
    <section className="modelQualityWorkspace">
      <div className="modelQualitySummaryGrid">
        <article>
          <span>Aktywny model</span>
          <strong>
            {activeIteration === null
              ? 'Model bazowy'
              : `Iteracja #${activeIteration.iterationNumber}`}
          </strong>
          <code>
            {activeIteration?.candidateManifestChecksumSha256
              ? shortChecksum(activeIteration.candidateManifestChecksumSha256)
              : 'Wbudowany model startowy'}
          </code>
        </article>
        <article>
          <span>Zweryfikowane plansze</span>
          <strong>{quality.resolvedLayoutCount.toLocaleString('pl-PL')}</strong>
          <small>Nowe od kohorty: {quality.newVerifiedLayoutCount}</small>
        </article>
        <article>
          <span>Zdjęcia źródłowe</span>
          <strong>{quality.sourceImageCount.toLocaleString('pl-PL')}</strong>
          <small>
            Próbki komórek: {quality.cellSampleCount.toLocaleString('pl-PL')}
          </small>
        </article>
        <article>
          <span>Ostatnia kohorta</span>
          <strong>
            {quality.latestCohort === null
              ? 'Brak'
              : `#${quality.latestCohort.iterationNumber}`}
          </strong>
          <code>
            {quality.latestCohort === null
              ? 'Jeszcze nie zamrożono danych'
              : shortChecksum(quality.latestCohort.manifestChecksumSha256)}
          </code>
        </article>
      </div>

      <div className="modelQualityColumns">
        <section
          className="modelQualityPanel"
          aria-labelledby="symbol-coverage-title"
        >
          <header>
            <h3 id="symbol-coverage-title">Pokrycie symboli</h3>
            <p>
              Pełna liczba ręcznie potwierdzonych cropów dla każdego symbolu.
            </p>
          </header>
          {quality.symbolCoverage.length === 0 ? (
            <p className="mutedText">Brak aktywnych symboli.</p>
          ) : (
            <ul className="symbolCoverageList">
              {quality.symbolCoverage.map((item) => (
                <li key={item.symbolCode}>
                  <code>{item.symbolCode}</code>
                  <strong>{item.sampleCount.toLocaleString('pl-PL')}</strong>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          className="modelQualityPanel"
          aria-labelledby="readiness-title"
        >
          <header>
            <h3 id="readiness-title">Gotowość iteracji</h3>
            <p>Progi 100 i 1000 są wskazówką, nie automatyczną blokadą.</p>
          </header>
          <ul className="modelQualityThresholds">
            {quality.advisoryThresholds.map((threshold) => (
              <li key={threshold.layoutCount}>
                <span aria-hidden="true">{threshold.reached ? '✓' : '○'}</span>
                <span>
                  {threshold.layoutCount.toLocaleString('pl-PL')} plansz
                </span>
                <strong>
                  {threshold.reached ? 'osiągnięty' : 'jeszcze nie'}
                </strong>
              </li>
            ))}
          </ul>
          <dl className="modelQualityDecisionCounts">
            <div>
              <dt>Oczekujące</dt>
              <dd>{quality.pendingItemCount}</dd>
            </div>
            <div>
              <dt>Odrzucone</dt>
              <dd>{quality.rejectedItemCount}</dd>
            </div>
            <div>
              <dt>Niekompletne</dt>
              <dd>{quality.incompleteItemCount}</dd>
            </div>
            <div>
              <dt>Chronione decyzje</dt>
              <dd>{quality.protectedItemCount}</dd>
            </div>
          </dl>
        </section>
      </div>

      <section
        className="modelQualityPanel"
        aria-labelledby="candidate-gate-title"
      >
        <header>
          <h3 id="candidate-gate-title">Ostatnia bramka kandydata</h3>
          <p>
            Raport ONNX i kalibracji. Kandydat nie zmienia aktywnego modelu bez
            osobnej aktywacji.
          </p>
        </header>
        {latestIteration === null ? (
          <p className="mutedText">Nie uruchomiono jeszcze żadnej iteracji.</p>
        ) : (
          <>
            <dl className="modelQualityDecisionCounts">
              <div>
                <dt>Iteracja</dt>
                <dd>#{latestIteration.iterationNumber}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{latestIteration.status}</dd>
              </div>
              <div>
                <dt>Test accuracy</dt>
                <dd>{typeof testAccuracy === 'number' ? testAccuracy : '—'}</dd>
              </div>
              <div>
                <dt>Test macro recall</dt>
                <dd>
                  {typeof testMacroRecall === 'number' ? testMacroRecall : '—'}
                </dd>
              </div>
            </dl>
            {latestIteration.rejectionReasons.length > 0 ? (
              <ul
                className="modelQualityWarnings"
                aria-label="Powody odrzucenia kandydata"
              >
                {latestIteration.rejectionReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : null}
            {latestIteration.gateReportRelativePath ? (
              <code
                title={latestIteration.gateReportChecksumSha256 ?? undefined}
              >
                {latestIteration.gateReportRelativePath}
              </code>
            ) : null}
          </>
        )}
      </section>

      <section
        className="modelQualityPanel"
        aria-labelledby="model-registry-title"
      >
        <header>
          <h3 id="model-registry-title">Rejestr i aktywacja modelu</h3>
          <p>
            Aktywacja i rollback dotyczą wyłącznie nowych jobów. Uruchomiony job
            zachowuje przypięty model i sumę kontrolną.
          </p>
        </header>
        <dl className="modelQualityDecisionCounts">
          <div>
            <dt>Aktywna iteracja</dt>
            <dd>{activeIterationId ?? 'Model bazowy'}</dd>
          </div>
          <div>
            <dt>Historia zmian</dt>
            <dd>{activations.length}</dd>
          </div>
        </dl>
        <div className="buttonRow">
          <button
            className="primaryButton"
            disabled={
              latestIteration === null ||
              latestIteration.status !== 'candidate_ready' ||
              latestIteration.id === activeIterationId ||
              activating
            }
            onClick={() =>
              latestIteration === null
                ? undefined
                : void prepareActivation('activate', latestIteration.id)
            }
            type="button"
          >
            Aktywuj ostatniego kandydata
          </button>
          <button
            className="secondaryButton"
            disabled={rollbackIterationId === null || activating}
            onClick={() =>
              rollbackIterationId === null
                ? undefined
                : void prepareActivation('rollback', rollbackIterationId)
            }
            type="button"
          >
            Przywróć poprzedni model
          </button>
        </div>
        {activations.length > 0 ? (
          <ol className="modelQualityActivationHistory">
            {activations.slice(0, 5).map((activation) => (
              <li key={activation.id}>
                <strong>{activation.action}</strong>{' '}
                <code>{activation.modelIterationId}</code>{' '}
                <time dateTime={activation.createdAt}>
                  {new Date(activation.createdAt).toLocaleString('pl-PL')}
                </time>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mutedText">Brak ręcznych zmian aktywnego modelu.</p>
        )}
        {activationPreview !== null ? (
          <section
            className="modelQualityConfirmation"
            aria-label="Potwierdzenie modelu"
          >
            <h3>
              {activationAction === 'rollback'
                ? 'Potwierdź rollback modelu'
                : 'Potwierdź aktywację modelu'}
            </h3>
            <code title={activationPreview.candidateManifestChecksumSha256}>
              SHA-256: {activationPreview.candidateManifestChecksumSha256}
            </code>
            <p>
              Iteracja: {activationPreview.modelIterationId}. Bieżąca iteracja:{' '}
              {activationPreview.currentModelIterationId ?? 'model bazowy'}.
            </p>
            <div className="buttonRow">
              <button
                className="primaryButton"
                disabled={activating || !activationPreview.canActivate}
                onClick={() => void applyActivation()}
                type="button"
              >
                {activating ? 'Zapisywanie…' : 'Potwierdź zmianę'}
              </button>
              <button
                className="secondaryButton"
                disabled={activating}
                onClick={() => setActivationPreview(null)}
                type="button"
              >
                Anuluj
              </button>
            </div>
          </section>
        ) : null}
      </section>

      <GridQualityPanel apiBaseUrl={apiBaseUrl} gameId={gameId} />

      {quality.warnings.length > 0 ? (
        <aside
          className="modelQualityWarnings"
          aria-label="Ostrzeżenia jakości"
        >
          <strong>Ostrzeżenia</strong>
          <ul>
            {quality.warnings.map((warning) => (
              <li key={warning}>{warningLabel(warning)}</li>
            ))}
          </ul>
        </aside>
      ) : null}

      {notice ? (
        <p className="modelQualityNotice" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="modelQualityError" role="alert">
          {error}
        </p>
      ) : null}

      {!confirming ? (
        <div className="buttonRow">
          <button
            className="primaryButton"
            disabled={!quality.canFreeze || loading}
            onClick={() => {
              setError('');
              setNotice('');
              setConfirming(true);
            }}
            type="button"
          >
            Ulepsz rozpoznawanie
          </button>
          <button
            className="secondaryButton"
            disabled={recalculating || pendingPreview?.pendingCount === 0}
            onClick={() => void recalculatePendingSymbols()}
            type="button"
          >
            {recalculating
              ? 'Przeliczanie…'
              : `Przelicz oczekujące (${pendingPreview?.pendingCount ?? '…'})`}
          </button>
        </div>
      ) : (
        <section
          className="modelQualityConfirmation"
          aria-label="Potwierdzenie manifestu"
        >
          <h3>Potwierdź niezmienny manifest</h3>
          <code title={preview.manifestChecksumSha256}>
            SHA-256: {preview.manifestChecksumSha256}
          </code>
          <dl>
            <div>
              <dt>Do treningu</dt>
              <dd>{preview.resolvedLayoutCount}</dd>
            </div>
            <div>
              <dt>Oczekujące</dt>
              <dd>{preview.pendingItemCount}</dd>
            </div>
            <div>
              <dt>Odrzucone</dt>
              <dd>{preview.rejectedItemCount}</dd>
            </div>
            <div>
              <dt>Niekompletne</dt>
              <dd>{preview.incompleteItemCount}</dd>
            </div>
            <div>
              <dt>Chronione</dt>
              <dd>{preview.protectedItemCount}</dd>
            </div>
          </dl>
          <p>
            Ta operacja zamrozi wskazaną wersję danych i uruchomi trwały trening
            w tle. Nie zmieni żadnej decyzji użytkownika ani aktywnego modelu.
          </p>
          <div className="buttonRow">
            <button
              className="primaryButton"
              disabled={freezing}
              onClick={() => void confirmFreeze()}
              type="button"
            >
              {freezing ? 'Zamrażanie…' : 'Potwierdź manifest'}
            </button>
            <button
              className="secondaryButton"
              disabled={freezing}
              onClick={() => setConfirming(false)}
              type="button"
            >
              Anuluj
            </button>
          </div>
        </section>
      )}
    </section>
  );
}
