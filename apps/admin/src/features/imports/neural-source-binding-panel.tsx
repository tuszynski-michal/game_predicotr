'use client';
import type {
  AdminApiClient,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryReviewSourceResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  buildNeuralSourceBinding,
  clearNeuralSourceDraft,
  confirmedNeuralRange,
  initialNeuralSourceDraft,
  neuralBindingMatchesProposal,
  readNeuralSourceDraft,
  writeNeuralSourceDraft,
  type NeuralSourceBindingDraft,
  type NeuralSourceDraftScope,
} from './neural-source-binding-state';

export function NeuralSourceBindingPanel({
  api,
  gameId,
  uploadId,
  source,
  imageUrl,
  preflightJobId,
  manifestChecksumSha256,
  onSaved,
  onRefresh,
}: {
  readonly api: Pick<AdminApiClient, 'createBrowserPageGeometryOverride'>;
  readonly gameId: string;
  readonly uploadId: string;
  readonly source: BrowserPageGeometryReviewSourceResponse;
  readonly imageUrl: string;
  readonly preflightJobId: string;
  readonly manifestChecksumSha256: string;
  readonly onSaved: () => void;
  readonly onRefresh: () => Promise<void>;
}) {
  const proposal = source.neuralProposal!;
  const savedHumanBinding =
    source.geometryOrigin === 'manual_override' &&
    source.existingOverrideRevision != null &&
    neuralBindingMatchesProposal(proposal, source.neuralProposalBinding);
  const scope = useMemo<NeuralSourceDraftScope>(
    () => ({
      gameId,
      uploadId,
      sourceChecksumSha256: proposal.sourceChecksumSha256,
      proposalChecksumSha256: proposal.proposalChecksumSha256,
      manifestChecksumSha256,
      overrideRevision: source.existingOverrideRevision ?? 0,
    }),
    [
      gameId,
      uploadId,
      proposal,
      manifestChecksumSha256,
      source.existingOverrideRevision,
    ],
  );
  const [draft, setDraft] = useState<NeuralSourceBindingDraft>(() =>
    initialNeuralSourceDraft(
      proposal,
      source.neuralProposalBinding,
      savedHumanBinding,
    ),
  );
  const [submittedCommand, setSubmittedCommand] =
    useState<BrowserPageGeometryOverrideCreate | null>(null);
  const [ready, setReady] = useState(false);
  const [draftConflict, setDraftConflict] = useState(false);
  const [imageState, setImageState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const mounted = useRef(true),
    submitting = useRef(false);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const stored = readNeuralSourceDraft(localStorage, scope);
        if (stored !== null) {
          setDraft(stored.draft);
          setSubmittedCommand(stored.submittedCommand);
        }
        setReady(true);
      } catch {
        setDraftConflict(true);
        setReady(true);
        setError(
          'Szkic ma inną propozycję, źródło lub rewizję. Rozpocznij nowy szkic na aktualnym kontekście.',
        );
      }
    });
    return () => {
      active = false;
      mounted.current = false;
    };
  }, [scope]);
  useEffect(() => {
    if (!ready || draftConflict) return;
    let active = true;
    try {
      writeNeuralSourceDraft(localStorage, scope, { draft, submittedCommand });
    } catch {
      queueMicrotask(() => {
        if (!active) return;
        setDraftConflict(true);
        setError(
          'Nie można utrwalić szkicu w przeglądarce. Przywróć dostęp do jej pamięci.',
        );
      });
    }
    return () => {
      active = false;
    };
  }, [draft, submittedCommand, ready, draftConflict, scope]);
  let range: ReturnType<typeof confirmedNeuralRange> | null = null,
    rangeError = '';
  try {
    range = confirmedNeuralRange(proposal, draft);
  } catch (cause) {
    rangeError = cause instanceof Error ? cause.message : 'Niepoprawny zakres.';
  }
  const count =
    range === null ? 0 : range.sequenceRangeEnd - range.sequenceRangeStart + 1;
  const slots = Array.from({ length: count }, (_, i) => i);
  let binding: ReturnType<typeof buildNeuralSourceBinding> | null = null,
    bindingError = '';
  try {
    binding = buildNeuralSourceBinding(proposal, draft);
  } catch (cause) {
    bindingError =
      cause instanceof Error ? cause.message : 'Sprawdź przypisania plansz.';
  }
  const locked = saving || submittedCommand !== null || draftConflict || !ready;
  function updateRange(field: 'rangeStart' | 'rangeEnd', value: string) {
    setDraft((current) => ({
      ...current,
      [field]: value,
      rangeConfirmed: false,
      choices: {},
      missing: [],
    }));
  }
  function reset() {
    try {
      clearNeuralSourceDraft(localStorage, scope);
    } catch {
      setError('Nie udało się usunąć starego szkicu.');
      return;
    }
    setDraft(
      initialNeuralSourceDraft(
        proposal,
        source.neuralProposalBinding,
        savedHumanBinding,
      ),
    );
    setSubmittedCommand(null);
    setDraftConflict(false);
    setError('');
    setNotice('');
  }
  async function save() {
    if (
      submitting.current ||
      imageState !== 'ready' ||
      !ready ||
      draftConflict ||
      (submittedCommand === null && binding === null)
    )
      return;
    const command: BrowserPageGeometryOverrideCreate = submittedCommand ?? {
      actor: 'local-owner',
      gameId,
      finalQuads: [],
      imageWidth: proposal.sourceWidth,
      imageHeight: proposal.sourceHeight,
      sourceChecksumSha256: proposal.sourceChecksumSha256,
      expectedOverrideRevision: scope.overrideRevision,
      geometryPreflightJobId: preflightJobId,
      geometryManifestChecksumSha256: manifestChecksumSha256,
      neuralProposalBinding: binding!,
    };
    try {
      writeNeuralSourceDraft(localStorage, scope, {
        draft,
        submittedCommand: command,
      });
    } catch {
      setDraftConflict(true);
      setError('Nie można utrwalić żądania do ponowienia. Nie wysłano zapisu.');
      return;
    }
    submitting.current = true;
    setSaving(true);
    setSubmittedCommand(command);
    setError('');
    setNotice('');
    try {
      const result = await api.createBrowserPageGeometryOverride(
        uploadId,
        command,
      );
      if (!mounted.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się potwierdzić przypisania. Ponów ten sam zapis lub odśwież kontekst.',
          ),
        );
        return;
      }
      try {
        clearNeuralSourceDraft(localStorage, scope);
      } catch {
        /* The server receipt is durable and the same request is idempotent. */
      }
      setNotice(
        'Zapisano przypisanie. Brakujące plansze zachowują swoje numery. Wyślij zapisane do weryfikacji.',
      );
      onSaved();
    } catch {
      if (mounted.current)
        setError(
          'Połączenie przerwano. Ponów zapis — odzyska tę samą decyzję.',
        );
    } finally {
      submitting.current = false;
      if (mounted.current) setSaving(false);
    }
  }
  return (
    <section aria-label="Przypisanie wykrytych plansz">
      <h4 style={{ overflowWrap: 'anywhere' }}>{source.sourceRelativePath}</h4>
      <p>
        Propozycje wymagają sprawdzenia. Przypisz każde wykrycie do właściwego
        numeru albo odrzuć je. Brak planszy nie zmienia kolejnych numerów.
      </p>
      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {!ready ? <p role="status">Odtwarzanie szkicu…</p> : null}
      {imageState === 'loading' ? (
        <p role="status">Wczytywanie zdjęcia źródłowego…</p>
      ) : null}
      {imageState === 'error' ? (
        <p role="alert">
          Nie udało się wczytać zdjęcia. Odśwież kontekst przed przypisywaniem
          plansz.
        </p>
      ) : null}
      <svg
        aria-label="Zdjęcie z propozycjami siatek"
        role="img"
        viewBox={`0 0 ${proposal.sourceWidth} ${proposal.sourceHeight}`}
        style={{ display: 'block', width: '100%', maxHeight: 650 }}
      >
        <image
          href={imageUrl}
          width={proposal.sourceWidth}
          height={proposal.sourceHeight}
          onLoad={() => setImageState('ready')}
          onError={() => setImageState('error')}
        />
        {imageState === 'ready'
          ? proposal.detections.map((d, index) =>
              d.structurallyValid && d.latticeNodes !== null ? (
                <g key={d.detectionId}>
                  <path
                    d={d.latticeNodes
                      .flatMap((p, i) => [
                        i % 6 < 5
                          ? `M${p.x},${p.y}L${d.latticeNodes![i + 1]!.x},${d.latticeNodes![i + 1]!.y}`
                          : '',
                        i < 18
                          ? `M${p.x},${p.y}L${d.latticeNodes![i + 6]!.x},${d.latticeNodes![i + 6]!.y}`
                          : '',
                      ])
                      .join(' ')}
                    fill="none"
                    stroke={
                      draft.choices[d.detectionId] === 'ignore'
                        ? '#888'
                        : '#ffcf3f'
                    }
                    strokeWidth={2}
                    strokeDasharray={
                      draft.choices[d.detectionId] === 'ignore'
                        ? '8 6'
                        : undefined
                    }
                  />
                  <text
                    x={d.latticeNodes[0]!.x}
                    y={d.latticeNodes[0]!.y - 6}
                    fill="white"
                    stroke="#111"
                    paintOrder="stroke"
                    strokeWidth={3}
                    fontSize={Math.max(16, proposal.sourceWidth / 45)}
                  >
                    {index + 1}
                    {draft.choices[d.detectionId] === 'ignore'
                      ? ' — odrzucona'
                      : ''}
                  </text>
                </g>
              ) : null,
            )
          : null}
      </svg>
      <fieldset disabled={locked} style={{ border: 0, padding: 0 }}>
        <legend>Potwierdź zakres plansz</legend>
        <p>
          Zakres z nazwy: {proposal.originalRange.sequenceRangeStart}–
          {proposal.originalRange.sequenceRangeEnd}. Koniec gry:{' '}
          {proposal.engineSnapshot.expectedLayoutCount}.
        </p>
        <label>
          Pierwsza plansza{' '}
          <input
            aria-label="Pierwsza plansza"
            inputMode="numeric"
            value={draft.rangeStart}
            onChange={(e) => updateRange('rangeStart', e.target.value)}
            style={{ minHeight: 44 }}
          />
        </label>{' '}
        <label>
          Ostatnia plansza{' '}
          <input
            aria-label="Ostatnia plansza"
            inputMode="numeric"
            value={draft.rangeEnd}
            onChange={(e) => updateRange('rangeEnd', e.target.value)}
            style={{ minHeight: 44 }}
          />
        </label>
        {rangeError ? <p role="alert">{rangeError}</p> : null}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            minHeight: 48,
          }}
        >
          <input
            type="checkbox"
            disabled={range === null}
            checked={draft.rangeConfirmed}
            onChange={(e) =>
              setDraft({ ...draft, rangeConfirmed: e.target.checked })
            }
          />
          Potwierdzam numery plansz widoczne na zdjęciu.
        </label>
      </fieldset>
      <fieldset
        disabled={locked || !draft.rangeConfirmed || range === null}
        style={{ border: 0, padding: 0 }}
      >
        <legend>Przypisz wykrycia do plansz</legend>
        {proposal.detections.length === 0 ? (
          <p>
            Sieć nie znalazła poprawnej planszy. Wszystkie pozycje wymagają
            ręcznej korekty.
          </p>
        ) : null}
        {proposal.detections.map((d, index) => (
          <label
            key={d.detectionId}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              minHeight: 48,
              flexWrap: 'wrap',
            }}
          >
            Propozycja {index + 1}
            {!d.structurallyValid ? ' — niepoprawna siatka' : ''}
            <select
              aria-label={`Przypisanie propozycji ${index + 1}`}
              value={draft.choices[d.detectionId] ?? ''}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  choices: {
                    ...current.choices,
                    [d.detectionId]: e.target.value,
                  },
                  missing: [],
                }))
              }
              style={{ minHeight: 44 }}
            >
              <option value="">Wybierz planszę</option>
              <option value="ignore">Odrzuć wykrycie</option>
              {d.structurallyValid && d.latticeNodes !== null
                ? slots.map((i) => (
                    <option key={i} value={String(i)}>
                      Plansza {range!.sequenceRangeStart + i}
                    </option>
                  ))
                : null}
            </select>
          </label>
        ))}
        <p>Pozycje w potwierdzonym zakresie:</p>
        {slots.map((i) => {
          const detection = proposal.detections.findIndex(
            (d) => draft.choices[d.detectionId] === String(i),
          );
          return detection >= 0 ? (
            <p key={i}>
              Plansza {range!.sequenceRangeStart + i}: propozycja{' '}
              {detection + 1}.
            </p>
          ) : (
            <label
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                minHeight: 48,
              }}
            >
              <input
                type="checkbox"
                checked={draft.missing.includes(i)}
                onChange={(e) =>
                  setDraft((current) => ({
                    ...current,
                    missing: e.target.checked
                      ? [...current.missing, i]
                      : current.missing.filter((v) => v !== i),
                  }))
                }
              />
              Plansza {range!.sequenceRangeStart + i}: potwierdzam brak
              wykrycia. Numer pozostaje bez zmian.
            </label>
          );
        })}
      </fieldset>
      {bindingError && draft.rangeConfirmed ? (
        <p role="status">{bindingError}</p>
      ) : null}
      <div className="importActionButtons">
        <button
          className="primaryButton"
          type="button"
          style={{ minHeight: 44 }}
          disabled={
            saving ||
            !ready ||
            draftConflict ||
            imageState !== 'ready' ||
            (submittedCommand === null && binding === null)
          }
          onClick={() => void save()}
        >
          {saving
            ? 'Zapisywanie…'
            : submittedCommand !== null
              ? 'Ponów ten sam zapis'
              : 'Zapisz przypisanie plansz'}
        </button>
        <button
          className="secondaryButton"
          type="button"
          style={{ minHeight: 44 }}
          disabled={saving}
          onClick={() => void onRefresh()}
        >
          Odśwież kontekst
        </button>
        <button
          className="secondaryButton"
          type="button"
          style={{ minHeight: 44 }}
          disabled={saving}
          onClick={reset}
        >
          Rozpocznij nowy szkic
        </button>
      </div>
    </section>
  );
}
