'use client';

import type {
  CleanupPreviewResponse,
  CleanupResultResponse,
} from '@game-predictor/admin-api-client';
import { useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  type CleanupClient,
  type CleanupTarget,
  executeCleanup,
  loadCleanupPreview,
} from '@/features/cleanup/cleanup-actions';

interface CleanupControlProps {
  readonly apiBaseUrl: string;
  readonly client?: CleanupClient;
  readonly onCompleted: (result: CleanupResultResponse) => void;
  readonly target: CleanupTarget;
  readonly targetLabel: string;
}

export function CleanupControl({
  apiBaseUrl,
  client,
  onCompleted,
  target,
  targetLabel,
}: CleanupControlProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [preview, setPreview] = useState<CleanupPreviewResponse | null>(null);
  const [typedTarget, setTypedTarget] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const [completed, setCompleted] = useState<CleanupResultResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const submitting = useRef(false);

  const isRelease = target.kind === 'mobile-release';
  const actionLabel = isRelease
    ? 'Usuń to wydanie'
    : 'Wyczyść dane layoutów gry';
  const canExecute =
    preview !== null &&
    preview.blockers.length === 0 &&
    typedTarget === preview.confirmationTarget &&
    acknowledged &&
    !executing;

  async function openPreview() {
    if (loading || executing) return;
    setLoading(true);
    setError('');
    setCompleted(null);
    setPreview(null);
    setTypedTarget('');
    setAcknowledged(false);
    const result = await loadCleanupPreview(api, target);
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setPreview(result.data);
  }

  async function submitCleanup() {
    if (!canExecute || preview === null || submitting.current) return;
    submitting.current = true;
    setExecuting(true);
    setError('');
    const result = await executeCleanup(api, target, preview);
    submitting.current = false;
    setExecuting(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setCompleted(result.data);
    onCompleted(result.data);
    setPreview(null);
  }

  return (
    <section className="cleanupControl" data-cleanup-kind={target.kind}>
      <div className="cleanupControlHeader">
        <div>
          <p className="eyebrow">Nieodwracalna operacja</p>
          <h3>{actionLabel}</h3>
          <p>
            {isRelease
              ? 'Usuwa rekord wydania oraz jego dedykowany snapshot, manifesty i APK.'
              : 'Zachowuje grę, ale usuwa jej importy, layouty, symbole, reguły, review i wydania.'}
          </p>
        </div>
        <button
          className="dangerButton"
          disabled={loading || executing}
          onClick={() => void openPreview()}
          type="button"
        >
          {loading ? 'Analizuję zależności…' : 'Pokaż zakres operacji'}
        </button>
      </div>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {completed !== null ? (
        <p className="feedbackBanner" role="status">
          {completed.alreadyCompleted
            ? 'Operacja była już ukończona; odtworzono jej zapisany wynik.'
            : `Operacja zakończona. Usunięto ${completed.deletedArtifactCount.toLocaleString(
                'pl-PL',
              )} zarządzanych artefaktów.`}
        </p>
      ) : null}

      {preview !== null ? (
        <div className="cleanupPreview">
          <div className="cleanupPreviewSummary">
            <strong>{targetLabel}</strong>
            <code>{preview.targetId}</code>
            <dl>
              {preview.counts
                .filter((entry) => entry.count > 0)
                .map((entry) => (
                  <div key={entry.name}>
                    <dt>{entry.name}</dt>
                    <dd>{entry.count.toLocaleString('pl-PL')}</dd>
                  </div>
                ))}
              <div>
                <dt>zarządzane artefakty</dt>
                <dd>{preview.artifactPaths.length.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>zachowane współdzielone</dt>
                <dd>
                  {preview.retainedSharedArtifactCount.toLocaleString('pl-PL')}
                </dd>
              </div>
            </dl>
          </div>

          {preview.artifactPaths.length > 0 ? (
            <details className="cleanupArtifacts">
              <summary>Ścieżki zarządzanych artefaktów</summary>
              <ul>
                {preview.artifactPaths.slice(0, 20).map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
              </ul>
              {preview.artifactPaths.length > 20 ? (
                <p>
                  oraz {preview.artifactPaths.length - 20} kolejnych ścieżek
                </p>
              ) : null}
            </details>
          ) : null}

          {preview.blockers.length > 0 ? (
            <div className="cleanupBlockers" role="alert">
              <strong>Operacja jest obecnie zablokowana</strong>
              <ul>
                {preview.blockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
              <button
                className="secondaryButton"
                onClick={() => void openPreview()}
                type="button"
              >
                Sprawdź ponownie
              </button>
            </div>
          ) : (
            <div className="cleanupConfirmation">
              <label>
                Wpisz dokładnie identyfikator celu
                <code>{preview.confirmationTarget}</code>
                <input
                  autoComplete="off"
                  onChange={(event) => setTypedTarget(event.target.value)}
                  spellCheck={false}
                  value={typedTarget}
                />
              </label>
              <label className="cleanupAcknowledgement">
                <input
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                  type="checkbox"
                />
                Rozumiem, że operacja jest nieodwracalna i dotyczy wyłącznie
                wskazanego celu.
              </label>
              <div className="rowActions">
                <button
                  className="secondaryButton"
                  disabled={executing}
                  onClick={() => setPreview(null)}
                  type="button"
                >
                  Anuluj
                </button>
                <button
                  className="dangerButton"
                  disabled={!canExecute}
                  onClick={() => void submitCleanup()}
                  type="button"
                >
                  {executing ? 'Usuwanie…' : actionLabel}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
