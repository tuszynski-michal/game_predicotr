'use client';

import type {
  AdminApiClient,
  ContentReferenceResponse,
  ContentTargetResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import { GridContentCanvas } from './grid-content-canvas';
import {
  ContentCommandNotice,
  useContentCommands,
} from './grid-content-command-control';
import {
  emptyContentCells,
  contentRoleLabel,
  type ContentCells,
  type ContentCommand,
} from './grid-content-state';

export type GridContentOrdinaryClient = Pick<
  AdminApiClient,
  | 'getGridCellContentReference'
  | 'writeGridCellContentReference'
  | 'gridContentTargetSourceUrl'
>;

/** Normal labels are intentionally loaded only by this controller, never by blind mode. */
export function GridContentOrdinary({
  api,
  apiBaseUrl,
  gameId,
  cohortId,
  manifestSha256,
  target,
}: {
  readonly api: GridContentOrdinaryClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly cohortId: string;
  readonly manifestSha256: string;
  readonly target: ContentTargetResponse;
}) {
  const [reference, setReference] = useState<ContentReferenceResponse | null>(
    null,
  );
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState('');
  const [notice, setNotice] = useState('');
  const [canvasEpoch, setCanvasEpoch] = useState(0);
  const [cells, setCells] = useState<ContentCells>(emptyContentCells);
  const [ready, setReady] = useState(false);
  const [approved, setApproved] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setReference(null);
      setReading(true);
      setReadError('');
      setReady(false);
      setApproved(false);
      setCanvasEpoch((v) => v + 1);
      void api
        .getGridCellContentReference(
          gameId,
          target.source.sourceId,
          target.positionIndex,
        )
        .then((result) => {
          if (!active) return;
          if (!result.data)
            throw new Error(
              apiErrorMessage(
                result.error,
                'Nie udało się odczytać bieżących etykiet.',
              ),
            );
          setReference(result.data);
        })
        .catch((failure) => {
          if (active) setReadError(String(failure));
        })
        .finally(() => {
          if (active) setReading(false);
        });
    });
    return () => {
      active = false;
    };
  }, [api, gameId, target.source.sourceId, target.positionIndex, refresh]);
  async function execute(command: ContentCommand) {
    if (command.kind !== 'reference')
      throw new Error(
        'Ten edytor zapisuje wyłącznie zwykłe etykiety zawartości.',
      );
    const result = await api.writeGridCellContentReference(
      gameId,
      command.body,
    );
    if (!result.data)
      throw new Error(
        apiErrorMessage(result.error, 'Nie potwierdzono etykiet.'),
      );
    if (result.data.idempotencyKey !== command.body.idempotencyKey)
      throw new Error('Odrzucono potwierdzenie innej komendy.');
    setNotice(
      'Zapisano etykiety zawartości. Geometria planszy i symbole nie zostały zmienione.',
    );
    setRefresh((v) => v + 1);
  }
  const control = useContentCommands(apiBaseUrl, gameId, 'ordinary', execute);
  const annotation = reference?.annotation;
  const sameTarget =
    annotation &&
    annotation.reference.positionIndex === target.positionIndex &&
    annotation.sequenceNumber === target.sequenceNumber &&
    annotation.source.sourceRepresentativeSha256 ===
      target.source.sourceRepresentativeSha256 &&
    annotation.source.width === target.source.width &&
    annotation.source.height === target.source.height;
  const initialCells = sameTarget ? annotation.reference.cells : undefined;
  const sourceReady =
    target.state === 'ready' &&
    target.sequenceNumber != null &&
    target.sequenceNumber > 0;
  return (
    <section
      className="gridContentWorkflow"
      aria-label="Zwykłe etykiety zawartości"
    >
      <h3>Etykiety zawartości — {contentRoleLabel(target.role)}</h3>
      <p>
        Pozycja {target.positionIndex + 1}, numer planszy{' '}
        {target.sequenceNumber ?? 'nieustalona'}. Oznaczasz grafikę pola, bez
        zatwierdzania geometrii ani klas symboli.
      </p>
      <ContentCommandNotice control={control} />
      {notice ? <p role="status">{notice}</p> : null}
      {readError ? <p role="alert">{readError}</p> : null}
      <button
        className="secondaryButton"
        type="button"
        disabled={reading || control.busy}
        aria-busy={reading}
        onClick={() => setRefresh((v) => v + 1)}
      >
        {reading ? 'Odczytywanie etykiet…' : 'Odśwież bieżące etykiety'}
      </button>
      {!sourceReady ? (
        <p role="alert">
          Cel ma nieustalony numer planszy lub tożsamość. Zapis zablokowany.{' '}
          {target.reasonCodes.join('; ')}
        </p>
      ) : null}
      {reference && sourceReady ? (
        <>
          <p>
            Rewizja zawartości: {reference.revision}.{' '}
            {annotation
              ? annotation.reference.humanApproved
                ? 'Poprzednie etykiety zatwierdził człowiek.'
                : 'Poprzednie etykiety nie są zatwierdzone.'
              : 'Brak dotychczasowych etykiet.'}
          </p>
          {annotation && !sameTarget ? (
            <p role="alert">
              Bieżąca etykieta dotyczy innego numeru planszy lub ramy źródła.
              Nie wypełnia edytora; wykonaj nową adnotację.
            </p>
          ) : null}
          {annotation?.origin === 'ai_proposal' ? (
            <p>
              Poprzedni zapis pochodzi z propozycji AI. Zatwierdzenie wymaga
              Twojego jawnego przeglądu.
            </p>
          ) : null}
          <GridContentCanvas
            key={`${gameId}:${target.source.sourceId}:${target.source.sourceSha256}:${target.positionIndex}:${reference.revision}:${canvasEpoch}`}
            sourceUrl={api.gridContentTargetSourceUrl(
              gameId,
              target.source.sourceId,
              { cohortId, manifestSha256 },
            )}
            width={target.source.width}
            height={target.source.height}
            initialCells={initialCells}
            disabled={control.blocked || reading}
            onChange={(c, _n, r) => {
              setCells(c);
              setReady(r);
            }}
          />
          <label>
            <input
              type="checkbox"
              checked={approved}
              disabled={control.blocked}
              onChange={(e) => setApproved(e.target.checked)}
            />{' '}
            Sprawdziłem zawartość wszystkich 15 pól i zatwierdzam własne
            etykiety
          </label>
          <div className="gridContentActions">
            <button
              className="secondaryButton"
              type="button"
              disabled={control.blocked || reading || !ready}
              onClick={() =>
                void control.send({
                  kind: 'reference',
                  body: {
                    idempotencyKey: crypto.randomUUID(),
                    sourceId: target.source.sourceId,
                    expectedSourceSha256: target.source.sourceSha256,
                    expectedPixelSha256:
                      target.source.sourceRepresentativeSha256,
                    positionIndex: target.positionIndex,
                    sequenceNumber: target.sequenceNumber!,
                    expectedRevision: reference.revision,
                    cells,
                    origin: 'manual',
                    humanApproval: false,
                  },
                })
              }
            >
              Zapisz etykiety bez zatwierdzenia
            </button>
            <button
              className="primaryButton"
              type="button"
              disabled={control.blocked || reading || !ready || !approved}
              onClick={() => {
                if (!approved) return;
                void control.send({
                  kind: 'reference',
                  body: {
                    idempotencyKey: crypto.randomUUID(),
                    sourceId: target.source.sourceId,
                    expectedSourceSha256: target.source.sourceSha256,
                    expectedPixelSha256:
                      target.source.sourceRepresentativeSha256,
                    positionIndex: target.positionIndex,
                    sequenceNumber: target.sequenceNumber!,
                    expectedRevision: reference.revision,
                    cells,
                    origin: 'manual',
                    humanApproval: true,
                  },
                });
              }}
            >
              Zapisz i zatwierdź etykiety zawartości
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
