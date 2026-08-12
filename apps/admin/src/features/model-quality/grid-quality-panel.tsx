'use client';

import type {
  GridCalibrationProfileResponse,
  GridProfileActivationAction,
  GridProfileActivationPreviewResponse,
  GridProfileActivationResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  confirmGridActivation,
  createGridCandidate,
  loadGridQuality,
  previewGridActivation,
  type GridQualityClient,
} from '@/features/model-quality/model-quality-actions';

const OWNER_ACTOR = 'local-owner';

function metric(
  profile: GridCalibrationProfileResponse | null,
  group: 'baseline' | 'candidate',
  key: 'meanNormalizedCornerError' | 'p95NormalizedCornerError',
): string {
  const rawGroup = profile?.gateMetrics[group];
  if (rawGroup === null || typeof rawGroup !== 'object') return '—';
  const value = (rawGroup as Record<string, unknown>)[key];
  return typeof value === 'number' ? value.toFixed(5) : '—';
}

export function GridQualityPanel({
  apiBaseUrl,
  client,
  gameId,
}: {
  readonly apiBaseUrl: string;
  readonly client?: GridQualityClient;
  readonly gameId: string;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [profiles, setProfiles] = useState<
    readonly GridCalibrationProfileResponse[]
  >([]);
  const [activations, setActivations] = useState<
    readonly GridProfileActivationResponse[]
  >([]);
  const [preview, setPreview] =
    useState<GridProfileActivationPreviewResponse | null>(null);
  const [action, setAction] = useState<GridProfileActivationAction>('activate');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const idempotencyKey = useRef<string | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      const result = await loadGridQuality(api, gameId, signal);
      if (signal?.aborted) return;
      if (!result.ok) {
        if (result.error !== 'REQUEST_ABORTED') setError(result.error);
      } else {
        setProfiles(result.profiles);
        setActivations(result.activations);
      }
      setLoading(false);
    },
    [api, gameId],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => void refresh(controller.signal));
    return () => controller.abort();
  }, [refresh]);

  const latest = profiles[0] ?? null;
  const activeId = activations[0]?.profileId ?? null;
  const rollbackId = activations[0]?.previousProfileId ?? null;

  async function createCandidate() {
    if (creating) return;
    setCreating(true);
    setError('');
    setNotice('');
    const result = await createGridCandidate(api, gameId);
    if (!result.ok) {
      setError(result.error);
    } else {
      setNotice(
        result.response.profile.status === 'candidate_ready'
          ? 'Kandydat przeszedł bramkę. Aktywuj go osobną akcją.'
          : 'Kandydat nie przeszedł bramki. Poprzedni profil pozostał bez zmian.',
      );
      await refresh();
    }
    setCreating(false);
  }

  async function prepareActivation(
    nextAction: GridProfileActivationAction,
    profileId: string,
  ) {
    setError('');
    setNotice('');
    const result = await previewGridActivation(api, {
      action: nextAction,
      gameId,
      profileId,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setAction(nextAction);
    setPreview(result.preview);
    idempotencyKey.current = null;
  }

  async function applyActivation() {
    if (preview === null || activating) return;
    setActivating(true);
    setError('');
    idempotencyKey.current ??= crypto.randomUUID();
    const result = await confirmGridActivation(api, {
      action,
      actor: OWNER_ACTOR,
      gameId,
      idempotencyKey: idempotencyKey.current,
      preview,
    });
    if (!result.ok) {
      setError(result.error);
      setActivating(false);
      return;
    }
    setNotice(
      action === 'rollback'
        ? 'Przywrócono profil. Zmiana dotyczy tylko nowych partii.'
        : 'Aktywowano profil. Zmiana dotyczy tylko nowych partii.',
    );
    setPreview(null);
    idempotencyKey.current = null;
    setActivating(false);
    await refresh();
  }

  return (
    <section className="modelQualityPanel" aria-labelledby="grid-quality-title">
      <header>
        <h3 id="grid-quality-title">Kalibracja siatki</h3>
        <p>
          Niezależny profil powstaje wyłącznie z zaakceptowanych korekt. Nigdy
          nie zmienia historycznych ani rozstrzygniętych plansz.
        </p>
      </header>
      <dl className="modelQualityDecisionCounts">
        <div>
          <dt>Aktywny profil</dt>
          <dd>{activeId ?? 'Detektor bazowy'}</dd>
        </div>
        <div>
          <dt>Ostatni kandydat</dt>
          <dd>{latest === null ? 'Brak' : `#${latest.profileNumber}`}</dd>
        </div>
        <div>
          <dt>Status bramki</dt>
          <dd>{latest?.status ?? '—'}</dd>
        </div>
        <div>
          <dt>Próbki walidacyjne</dt>
          <dd>
            {typeof latest?.gateMetrics.validationSampleCount === 'number'
              ? latest.gateMetrics.validationSampleCount
              : '—'}
          </dd>
        </div>
        <div>
          <dt>Średni błąd: baza → kandydat</dt>
          <dd>
            {metric(latest, 'baseline', 'meanNormalizedCornerError')} →{' '}
            {metric(latest, 'candidate', 'meanNormalizedCornerError')}
          </dd>
        </div>
        <div>
          <dt>P95: baza → kandydat</dt>
          <dd>
            {metric(latest, 'baseline', 'p95NormalizedCornerError')} →{' '}
            {metric(latest, 'candidate', 'p95NormalizedCornerError')}
          </dd>
        </div>
      </dl>
      {latest !== null && latest.rejectionReasons.length > 0 ? (
        <ul className="modelQualityWarnings">
          {latest.rejectionReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      <div className="buttonRow">
        <button
          className="primaryButton"
          disabled={creating || loading}
          onClick={() => void createCandidate()}
          type="button"
        >
          {creating ? 'Budowanie…' : 'Ulepsz cięcie siatki'}
        </button>
        <button
          className="secondaryButton"
          disabled={
            latest === null ||
            latest.status !== 'candidate_ready' ||
            latest.id === activeId ||
            activating
          }
          onClick={() =>
            latest === null
              ? undefined
              : void prepareActivation('activate', latest.id)
          }
          type="button"
        >
          Aktywuj kandydata
        </button>
        <button
          className="secondaryButton"
          disabled={rollbackId === null || activating}
          onClick={() =>
            rollbackId === null
              ? undefined
              : void prepareActivation('rollback', rollbackId)
          }
          type="button"
        >
          Przywróć profil
        </button>
      </div>
      {preview !== null ? (
        <section
          className="modelQualityConfirmation"
          aria-label="Profil siatki"
        >
          <h3>Potwierdź zmianę profilu siatki</h3>
          <code>{preview.profileChecksumSha256}</code>
          <p>Zmiana zostanie przypięta dopiero do następnego nowego joba.</p>
          <div className="buttonRow">
            <button
              className="primaryButton"
              disabled={activating || !preview.canActivate}
              onClick={() => void applyActivation()}
              type="button"
            >
              {activating ? 'Zapisywanie…' : 'Potwierdź zmianę'}
            </button>
            <button
              className="secondaryButton"
              disabled={activating}
              onClick={() => setPreview(null)}
              type="button"
            >
              Anuluj
            </button>
          </div>
        </section>
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
    </section>
  );
}
