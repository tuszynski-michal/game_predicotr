'use client';

import type {
  AdminApiClient,
  GridValidationComponentChoice,
  GridCorrectionLearningPreviewCommand,
} from '@game-predictor/admin-api-client';
import { useRef, useState } from 'react';
import { reasonLabel } from './grid-model-state';

export type ValidationAssignments = NonNullable<
  GridCorrectionLearningPreviewCommand['validationAssignments']
>;
export const VALIDATION_POLICY = 'application-grid-corrections-v4' as const;
export const orderedAssignments = (value: ValidationAssignments) =>
  Object.fromEntries(
    Object.entries(value).sort(([a], [b]) => a.localeCompare(b)),
  ) as ValidationAssignments;

/** The server supplies the complete closure and choices; the client never groups. */
export function GridValidationPurposeSelector({
  components,
  value,
  onChange,
  disabled,
  loaded = false,
  emptyActionLabel = 'Sprawdź zakres/podział',
}: {
  readonly components: readonly GridValidationComponentChoice[];
  readonly value: ValidationAssignments;
  readonly onChange: (value: ValidationAssignments) => void;
  readonly disabled: boolean;
  readonly loaded?: boolean;
  readonly emptyActionLabel?: string;
}) {
  return (
    <section aria-label="Przeznaczenie kontroli A i B">
      <p>
        A wybiera ustawienia modelu. B jest oddzielnym testem automatu; nie
        służy do uczenia ani wyboru ustawień. Bufor zachowuje chroniony odstęp.
        Brak B nie blokuje inaczej dozwolonego treningu; automat pozostaje bez
        kwalifikacji. Minima i bufory sprawdza podgląd.
      </p>
      {components.length ? (
        components.map((component) => {
          const selected = [
            ...new Set(
              component.sources
                .map((source) => value[source.sourceId])
                .filter(Boolean),
            ),
          ];
          return (
            <fieldset key={component.componentKey} disabled={disabled}>
              <legend>
                {component.sources[0]?.displayName || 'Zdjęcia bez nazwy'}
                {component.sources.length > 1
                  ? ` i ${component.sources.length - 1} powiązanych zdjęć`
                  : ''}
              </legend>
              <details>
                <summary>Zdjęcia i ochrona grupy</summary>
                <ul>
                  {component.sources.map((source) => (
                    <li key={source.sourceId}>
                      {source.displayName}; zakres{' '}
                      {source.rangeStart ?? 'nieznany'}–
                      {source.rangeEnd ?? 'nieznany'}; ludzkie etykiety
                      geometrii: {source.qualifiedBoards}/9.
                    </li>
                  ))}
                </ul>
                <p>
                  Dotychczasowe role:{' '}
                  {component.priorRoles.join(', ') || 'brak'}; przeznaczenie:{' '}
                  {component.priorPurposes.join(', ') || 'nieprzypisane'}.
                </p>
                {component.options
                  .filter((option) => !option.allowed)
                  .map((option) => (
                    <p key={option.purpose}>
                      {option.purpose}:{' '}
                      {option.reasonCodes.map(reasonLabel).join(', ')}
                    </p>
                  ))}
              </details>
              <label>
                Przeznaczenie grupy powiązanych zdjęć{' '}
                <select
                  aria-label={`Przeznaczenie ${component.sources[0]?.displayName}`}
                  value={selected.length === 1 ? selected[0] : ''}
                  disabled={!component.options.some((option) => option.allowed)}
                  onChange={(event) => {
                    const next = { ...value };
                    for (const source of component.sources) {
                      delete next[source.sourceId];
                      if (event.target.value)
                        next[source.sourceId] = event.target.value as
                          'A' | 'B' | 'BUFFER';
                    }
                    onChange(orderedAssignments(next));
                  }}
                >
                  <option value="">Zachowaj dotychczasowy podział</option>
                  {component.options.map((option) => (
                    <option
                      key={option.purpose}
                      value={option.purpose}
                      disabled={!option.allowed}
                    >
                      {option.purpose === 'BUFFER' ? 'Bufor' : option.purpose}
                    </option>
                  ))}
                </select>
              </label>
            </fieldset>
          );
        })
      ) : (
        <p>
          {loaded
            ? 'Podgląd nie zwrócił dostępnych grup powiązanych zdjęć. Sprawdź przyczyny i zakres importów.'
            : `Lista grup powiązanych zdjęć nie została jeszcze odczytana. Kliknij „${emptyActionLabel}”. Odczyt nie zapisuje podziału.`}
        </p>
      )}
      <p>
        Wybór jest lokalny do czasu podglądu i zamrożenia. Odrzucenie podglądu
        niczego nie rezerwuje.
      </p>
    </section>
  );
}

/** Independent existing-cohort recovery can read choices despite shared-history blockers. */
export function GridValidationPurposePreview({
  api,
  gameId,
  mode,
  importJobIds,
  value,
  onChange,
  disabled,
}: {
  readonly api: Pick<AdminApiClient, 'previewGridCorrectionLearning'>;
  readonly gameId: string;
  readonly mode: 'grid-only' | 'screen+grid';
  readonly importJobIds: string[];
  readonly value: ValidationAssignments;
  readonly onChange: (value: ValidationAssignments) => void;
  readonly disabled: boolean;
}) {
  const [components, setComponents] = useState<GridValidationComponentChoice[]>(
    [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const inFlight = useRef(false);
  async function read() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.previewGridCorrectionLearning(gameId, {
        trainingMode: mode,
        policyVersion: VALIDATION_POLICY,
        validationAssignments: orderedAssignments(value),
        importJobIds,
        exclusions: [],
      });
      if (
        !result.data ||
        result.data.gameId !== gameId ||
        result.data.policyVersion !== VALIDATION_POLICY ||
        !result.data.validationComponents
      )
        throw new Error(
          'Nie udało się odczytać chronionych grup zdjęć tej gry.',
        );
      setComponents(result.data.validationComponents);
      setLoaded(true);
      if (result.data.blockers.length)
        setError(result.data.blockers.map(reasonLabel).join(', '));
    } catch (failure) {
      setError(String(failure));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="secondaryButton"
        type="button"
        disabled={disabled || busy || !importJobIds.length}
        aria-busy={busy}
        onClick={() => void read()}
      >
        {busy
          ? 'Odczytywanie grup zdjęć…'
          : 'Odczytaj grupy powiązanych zdjęć (A/B)'}
      </button>
      {error ? <p role="status">{error}</p> : null}
      <GridValidationPurposeSelector
        components={components}
        value={value}
        onChange={onChange}
        disabled={disabled || busy}
        loaded={loaded}
        emptyActionLabel="Odczytaj grupy powiązanych zdjęć (A/B)"
      />
    </>
  );
}
