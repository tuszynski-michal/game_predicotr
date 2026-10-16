import type {
  QualityAssessCommand,
  QualityMemberResponse,
  QualityMeasurementResponse,
  QualityPositionJudgment,
} from '@game-predictor/admin-api-client';
import { useState } from 'react';
import type { MeasurementCommand } from './grid-quality-measurement-command';
import {
  measurementJudgments,
  measurementMesh,
  measurementReviewerUrl,
} from './grid-quality-measurement-state';

const labels: Record<string, string> = {
  correct: 'Poprawna',
  incorrect: 'Błędna',
  not_assessable: 'Niemożliwa do oceny',
  unknown: 'Nieznana',
  unreviewed: 'Nieoceniona',
};

export function GridQualityMeasurementMember({
  member,
  measurement,
  apiBaseUrl,
  disabled,
  onCommand,
}: {
  readonly member: QualityMemberResponse;
  readonly measurement: QualityMeasurementResponse;
  readonly apiBaseUrl: string;
  readonly disabled: boolean;
  readonly onCommand: (command: MeasurementCommand) => void;
}) {
  const [positions, setPositions] = useState(() =>
    measurementJudgments(member),
  );
  const [unexpected, setUnexpected] = useState<
    NonNullable<QualityAssessCommand['unexpected']>
  >(() =>
    member.unexpectedDetections.map(
      (_, index) =>
        member.unexpectedJudgments.find((item) => item.index === index) ?? {
          index,
          verdict: 'unreviewed',
        },
    ),
  );
  const [imageLoaded, setImageLoaded] = useState(false);
  const [currentImageLoaded, setCurrentImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const sourceUrl = `${apiBaseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(measurement.gameId)}/grid-quality-measurements/${encodeURIComponent(measurement.measurementId)}/sources/${encodeURIComponent(member.sourceId)}/asset`;
  const width = Number(member.source.oriented_width ?? member.source.width),
    height = Number(member.source.oriented_height ?? member.source.height);
  const dimensionsValid =
    Number.isFinite(width) &&
    width > 0 &&
    Number.isFinite(height) &&
    height > 0;
  const canSee =
    imageLoaded && !imageError && member.available && dimensionsValid;
  const reviewer =
    typeof window !== 'undefined'
      ? measurementReviewerUrl(window.location.origin)
      : null;
  const completePositions =
    member.positions.length === 9 &&
    new Set(member.positions.map((p) => p.positionIndex)).size === 9 &&
    member.positions.every((p) => p.positionIndex >= 0 && p.positionIndex <= 8);
  const judgmentsVisible =
    positions.every((judgment) => {
      const position = member.positions.find(
        (item) => item.positionIndex === judgment.positionIndex,
      );
      const geometryVisible =
        canSee &&
        !!position?.original.available &&
        measurementMesh(position.original).length > 0;
      return (
        (!['correct', 'incorrect'].includes(judgment.geometry) ||
          geometryVisible) &&
        (canSee || !['correct', 'incorrect'].includes(judgment.detection)) &&
        (canSee || !['correct', 'incorrect'].includes(judgment.sequence))
      );
    }) &&
    (canSee ||
      unexpected.every(
        (item) => !['correct', 'incorrect'].includes(item.verdict),
      ));

  function update(
    index: number,
    axis: 'geometry' | 'detection' | 'sequence',
    value: string,
  ) {
    setPositions((old) =>
      old.map((item) =>
        item.positionIndex === index
          ? ({ ...item, [axis]: value } as QualityPositionJudgment)
          : item,
      ),
    );
  }

  return (
    <section aria-label={`Zdjęcie ${member.sampleKind} ${member.sourceId}`}>
      <h4>
        {member.sampleKind === 'random' ? 'Próba losowa' : 'Trudny przykład'}:{' '}
        {member.sourceId}
      </h4>
      <p>
        Nagranie:{' '}
        {member.recordingStatus === 'declared'
          ? 'zadeklarowane'
          : 'unresolved — niezależność niepotwierdzona'}
        . Rewizja oceny: {member.revision}.
      </p>
      {!member.available || imageError ? (
        <p role="alert">
          Obraz niedostępny:{' '}
          {member.unavailableReason ?? 'Nie udało się załadować zdjęcia.'}
        </p>
      ) : null}
      {!dimensionsValid ? (
        <p role="alert">
          Brak prawidłowych wymiarów zdjęcia. Ocena geometrii jest niedostępna.
        </p>
      ) : null}
      {!completePositions ? (
        <p role="alert">
          Niepełne dane dziewięciu pozycji. Zapis jest zablokowany.
        </p>
      ) : null}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 16,
        }}
      >
        {(['original', 'current'] as const).map((kind) => (
          <figure key={kind} style={{ margin: 0 }}>
            <figcaption>
              {kind === 'original'
                ? 'Oryginalna obserwacja modelu — oceniasz ten wynik'
                : 'Bieżąca geometria zamrożona przy utworzeniu próby — current-only'}
            </figcaption>
            {member.available && dimensionsValid ? (
              <div style={{ position: 'relative' }}>
                {/* Exact oriented source image and frozen pixel coordinates share one viewport. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={sourceUrl}
                  alt={`${kind === 'original' ? 'Oryginał' : 'Bieżąca geometria'} ${member.sourceId}`}
                  style={{ display: 'block', width: '100%', height: 'auto' }}
                  onLoad={() => {
                    if (kind === 'original') {
                      setImageLoaded(true);
                      setImageError(false);
                    } else setCurrentImageLoaded(true);
                  }}
                  onError={() => {
                    if (kind === 'original') {
                      setImageLoaded(false);
                      setImageError(true);
                    } else setCurrentImageLoaded(false);
                  }}
                />
                <svg
                  aria-label={`${kind} dziewięć pozycji`}
                  viewBox={`0 0 ${width} ${height}`}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    pointerEvents: 'none',
                  }}
                >
                  {Array.from({ length: 9 }, (_, index) => {
                    const position = member.positions.find(
                      (p) => p.positionIndex === index,
                    );
                    const observation = position?.[kind];
                    const lines = observation
                      ? measurementMesh(observation)
                      : [];
                    const first = observation?.nodes?.[0]?.[0];
                    return (
                      <g
                        key={index}
                        stroke={kind === 'original' ? '#00ffff' : '#ffdc00'}
                        strokeWidth={Math.max(width / 700, 1)}
                        fill="none"
                      >
                        {lines.map((line, lineIndex) => (
                          <polyline key={lineIndex} points={line} />
                        ))}
                        {first && lines.length ? (
                          <text
                            x={first.x}
                            y={first.y}
                            fill="white"
                            stroke="black"
                            paintOrder="stroke"
                            fontSize={Math.max(width / 45, 12)}
                          >
                            {index + 1}
                          </text>
                        ) : null}
                      </g>
                    );
                  })}
                </svg>
              </div>
            ) : (
              <p>Brak obrazu do pokazania.</p>
            )}
          </figure>
        ))}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 12,
        }}
      >
        {positions.map((judgment) => {
          const position = member.positions.find(
            (item) => item.positionIndex === judgment.positionIndex,
          );
          const originalVisible =
            canSee &&
            !!position?.original.available &&
            measurementMesh(position.original).length > 0;
          const currentVisible =
            canSee &&
            currentImageLoaded &&
            !!position?.current.available &&
            measurementMesh(position.current).length > 0;
          return (
            <fieldset key={judgment.positionIndex} disabled={disabled}>
              <legend>
                Pozycja {judgment.positionIndex + 1} (wiersz{' '}
                {Math.floor(judgment.positionIndex / 3) + 1}, kolumna{' '}
                {(judgment.positionIndex % 3) + 1})
              </legend>
              <p>
                Sekwencja: {position?.sequenceNumber ?? 'nieznana'}. Własność:{' '}
                {position?.ownership ?? 'unknown'}.
              </p>
              {!originalVisible ? (
                <p>
                  Oryginalna predykcja niedostępna:{' '}
                  {position?.original.reason ??
                    'Brak ocenialnych węzłów lub obrazu.'}{' '}
                  To luka pokrycia, nie dowód błędu detektora.
                </p>
              ) : null}
              {position?.current.reason ? (
                <p>Bieżąca geometria: {position.current.reason}</p>
              ) : null}
              <details>
                <summary>Pochodzenie oryginalnej obserwacji</summary>
                <pre
                  style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
                >
                  {position?.original.producer
                    ? JSON.stringify(position.original.producer, null, 2)
                    : 'Brak udokumentowanego producenta. Bieżący przydział modelu nie potwierdza historycznej predykcji.'}
                </pre>
                <p>Odcisk celu: {position?.targetSha256 ?? 'brak'}</p>
              </details>
              {(['geometry', 'detection', 'sequence'] as const).map((axis) => (
                <label key={axis} style={{ display: 'block', marginBlock: 8 }}>
                  {
                    {
                      geometry: 'Geometria',
                      detection: 'Detekcja',
                      sequence: 'Sekwencja',
                    }[axis]
                  }{' '}
                  {judgment.positionIndex + 1}
                  <select
                    aria-label={`${axis} ${judgment.positionIndex + 1}`}
                    value={judgment[axis]}
                    onChange={(e) =>
                      update(judgment.positionIndex, axis, e.target.value)
                    }
                  >
                    {(axis === 'geometry'
                      ? ['unreviewed', 'correct', 'incorrect', 'not_assessable']
                      : ['unreviewed', 'correct', 'incorrect', 'unknown']
                    ).map((value) => (
                      <option
                        key={value}
                        value={value}
                        disabled={
                          (value === 'correct' || value === 'incorrect') &&
                          (axis === 'geometry' ? !originalVisible : !canSee)
                        }
                      >
                        {labels[value]}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <p>
                Symbole: {position?.currentManualSymbolCount ?? 0}/
                {position?.currentSymbolCellCount ?? 0} aktualnych ręcznych
                potwierdzeń. Skuteczność klasyfikatora: niezmierzona.
              </p>
              <button
                type="button"
                disabled={
                  disabled ||
                  !currentVisible ||
                  !position?.approvalEligible ||
                  !position.reviewItemId
                }
                onClick={() => {
                  if (
                    !position?.reviewItemId ||
                    !currentVisible ||
                    !position.approvalEligible
                  )
                    return;
                  onCommand({
                    kind: 'approve',
                    reviewItemId: position.reviewItemId,
                    importJobId: member.importJobId,
                    body: {
                      idempotencyKey: crypto.randomUUID(),
                      measurementId: measurement.measurementId,
                      sourceId: member.sourceId,
                      sampleKind: member.sampleKind,
                      positionIndex: position.positionIndex,
                      manifestSha256: measurement.manifestSha256,
                      targetSha256: position.targetSha256,
                    },
                  });
                }}
              >
                Zatwierdzam pokazaną bieżącą geometrię bez zmiany — pozycja{' '}
                {judgment.positionIndex + 1}
              </button>
              {!position?.approvalEligible && position?.approvalBlocker ? (
                <p
                  aria-label={`Powód niedostępności zatwierdzenia ${judgment.positionIndex + 1}`}
                >
                  {position.approvalBlocker ===
                  'IMAGE_GRID_REVIEW_ITEM_NOT_FOUND'
                    ? 'Plansza nie jest dostępna do zatwierdzenia. Jeżeli import trwa, poczekaj na jego zakończenie i odśwież pomiar.'
                    : 'Tej geometrii nie można teraz zatwierdzić. Odśwież pomiar i sprawdź bieżący stan planszy w Reviewerze.'}
                </p>
              ) : null}
              <p>
                Ten przycisk zatwierdza wyłącznie pokazaną geometrię
                current-only zamrożoną przy utworzeniu próby. Nie ocenia
                oryginalnego wyniku modelu. Zmieniony cel wymaga ponownego
                obejrzenia i osobnej korekty.
              </p>
            </fieldset>
          );
        })}
      </div>
      <section aria-label="Nieoczekiwane detekcje">
        <h5>Nieoczekiwane detekcje: {member.unexpectedDetections.length}</h5>
        {member.unexpectedDetections.map((item, index) => (
          <div key={index}>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify(item, null, 2)}
            </pre>
            <label>
              Ocena detekcji dodatkowej {index + 1}
              <select
                disabled={disabled}
                value={unexpected[index]?.verdict ?? 'unreviewed'}
                onChange={(e) =>
                  setUnexpected((old) =>
                    old.map((v) =>
                      v.index === index
                        ? { ...v, verdict: e.target.value as typeof v.verdict }
                        : v,
                    ),
                  )
                }
              >
                {['unreviewed', 'correct', 'incorrect', 'unknown'].map(
                  (value) => (
                    <option
                      key={value}
                      value={value}
                      disabled={
                        !canSee && ['correct', 'incorrect'].includes(value)
                      }
                    >
                      {labels[value]}
                    </option>
                  ),
                )}
              </select>
            </label>
          </div>
        ))}
      </section>
      <p>
        Zapis oceny zachowuje pierwotny wynik. Zatwierdzenie geometrii wymaga
        osobnego przycisku.
      </p>
      <button
        type="button"
        disabled={
          disabled ||
          !completePositions ||
          !measurement.manifestAvailable ||
          !judgmentsVisible
        }
        onClick={() =>
          onCommand({
            kind: 'assess',
            measurementId: measurement.measurementId,
            body: {
              idempotencyKey: crypto.randomUUID(),
              sourceId: member.sourceId,
              sampleKind: member.sampleKind,
              expectedRevision: member.revision,
              manifestSha256: measurement.manifestSha256,
              positions: [
                positions[0],
                positions[1],
                positions[2],
                positions[3],
                positions[4],
                positions[5],
                positions[6],
                positions[7],
                positions[8],
              ],
              unexpected,
            },
          })
        }
      >
        Zapisz jawne oceny dziewięciu pozycji
      </button>
      {reviewer ? (
        <p>
          <a href={reviewer} target="_blank" rel="noreferrer">
            Otwórz Reviewer
          </a>
          . Ręcznie wybierz grę {measurement.gameId}, import{' '}
          {member.importJobId}, zdjęcie {member.sourceId} i właściwą pozycję.
        </p>
      ) : null}
    </section>
  );
}
