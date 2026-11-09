'use client';

import type {
  AdminApiClient,
  GridGeometryProposalResponse,
  OperationalImageReviewItemResponse,
  ProposalCandidatesResponse,
  ProposalDiscoveryResponse,
  OperationalImageReviewGeometryPreviewCommand,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  operationalBoardGeometryTarget,
  type OperationalBoardGeometryClient,
  type BoardGeometryCorrectionTarget,
} from './board-geometry-correction-target';
import {
  parseBoardLattice,
  boardLatticeTransportCorners,
} from './board-lattice-state';
import { BoardGeometryCorrectionEditor } from './deferred-board-cell-geometry-editor';
import { operationalReviewAssetUrl } from './operational-review-state';

export type GridGeometryProposalsClient = OperationalBoardGeometryClient &
  Partial<
    Pick<
      AdminApiClient,
      | 'listOperationalGridGeometryProposals'
      | 'createOperationalGridGeometryProposal'
      | 'acceptOperationalGridGeometryProposal'
      | 'rejectOperationalGridGeometryProposal'
    >
  >;

/** Persist command identity before network I/O, including a lost create response. */
export function proposalCommandKey(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  scope: string,
  command: unknown,
): string {
  const key = `grid-proposal-command:${scope}`;
  const canonical = JSON.stringify(command);
  const saved = storage.getItem(key);
  if (saved !== null) {
    const value = JSON.parse(saved) as { command: string; key: string };
    if (value.command === canonical) return value.key;
  }
  const id = crypto.randomUUID();
  storage.setItem(key, JSON.stringify({ command: canonical, key: id }));
  return id;
}

function modelLabel(pin: Record<string, unknown>): string {
  const model = (pin.model ?? pin.catalogueManifest ?? pin) as Record<
    string,
    unknown
  >;
  return [
    model.version ?? model.modelVersion ?? model.profileId ?? 'V3',
    model.manifestChecksumSha256 ??
      model.weightsSha256 ??
      model.weightsChecksumSha256 ??
      pin.catalogueManifestSha256 ??
      '',
  ].join(' · ');
}

export function GridGeometryProposals({
  api,
  apiBaseUrl,
  importJobId,
  item,
  onChanged,
  onEditingChange,
  onRejected,
}: {
  readonly api: GridGeometryProposalsClient;
  readonly apiBaseUrl: string;
  readonly importJobId: string;
  readonly item: OperationalImageReviewItemResponse;
  readonly onChanged: () => void;
  readonly onRejected?: () => void;
  readonly onEditingChange?: (editing: boolean) => void;
}) {
  const [data, setData] = useState<ProposalCandidatesResponse | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<GridGeometryProposalResponse | null>(
    null,
  );
  useEffect(() => {
    onEditingChange?.(editing !== null);
    return () => onEditingChange?.(false);
  }, [editing, onEditingChange]);
  const dialog = useRef<HTMLDialogElement>(null);
  const context = useMemo(
    () => ({ gameId: item.gameId, importJobId }),
    [item.gameId, importJobId],
  );
  useEffect(() => {
    let active = true;
    if (api.listOperationalGridGeometryProposals === undefined) return;
    api
      .listOperationalGridGeometryProposals(item.id, context)
      .then((result) => {
        if (!active) return;
        if (result.data !== undefined) setData(result.data);
        else
          setMessage(
            apiErrorMessage(result.error, 'Nie udało się odczytać propozycji.'),
          );
      })
      .catch(() => {
        if (active)
          setMessage('Połączenie zostało przerwane. Odśwież propozycje.');
      });
    return () => {
      active = false;
    };
  }, [api, item.id, item.geometryRevision, item.resolutionRevision, context]);
  useEffect(() => {
    if (editing !== null && !dialog.current?.open) dialog.current?.showModal();
    if (editing === null && dialog.current?.open) dialog.current.close();
  }, [editing]);

  async function ensureProposal(
    candidate: GridGeometryProposalResponse | ProposalDiscoveryResponse,
  ) {
    if ('id' in candidate) return candidate;
    if (api.createOperationalGridGeometryProposal === undefined)
      throw new Error('Propozycje są niedostępne.');
    const command = { targetResultId: candidate.targetResultId };
    const idempotencyKey = proposalCommandKey(
      localStorage,
      `${item.gameId}:${item.id}:create:${candidate.targetResultId}`,
      command,
    );
    const result = await api.createOperationalGridGeometryProposal(
      item.id,
      context,
      { ...command, idempotencyKey },
    );
    if (result.data?.current == null)
      throw new Error(
        apiErrorMessage(
          result.error,
          'Nie udało się przygotować propozycji. Odśwież planszę.',
        ),
      );
    return result.data.current;
  }

  async function act(
    candidate: GridGeometryProposalResponse | ProposalDiscoveryResponse,
    action: 'accept' | 'edit' | 'reject',
  ) {
    setBusy(true);
    setMessage('');
    try {
      const proposal = await ensureProposal(candidate);
      if (
        proposal.state !== 'pending' ||
        (!proposal.applicable && action !== 'reject')
      ) {
        setData((old) => ({
          candidates: [],
          proposals: [
            proposal,
            ...(old?.proposals.filter((p) => p.id !== proposal.id) ?? []),
          ],
        }));
        setMessage(
          'Odczytano wcześniejszą decyzję. Bieżąca geometria wymaga odświeżenia.',
        );
        if (proposal.state === 'accepted') onChanged();
        return;
      }
      if (action === 'edit') {
        setEditing(proposal);
        return;
      }
      const common = { expectedProposalRevision: proposal.revision };
      const body =
        action === 'reject'
          ? common
          : {
              ...common,
              expectedGeometryRevision:
                proposal.candidate.expectedGeometryRevision,
              expectedResolutionRevision:
                proposal.candidate.expectedResolutionRevision,
              originalCandidateSha256:
                proposal.candidate.originalCandidateSha256,
              mode: 'model' as const,
              ...(item.manualCropPolicyVersion == null
                ? {}
                : { cropPolicyVersion: item.manualCropPolicyVersion }),
            };
      const key = proposalCommandKey(
        localStorage,
        `${item.gameId}:${proposal.id}:${action}`,
        body,
      );
      const result =
        action === 'reject'
          ? await api.rejectOperationalGridGeometryProposal?.(
              item.id,
              proposal.id,
              context,
              { ...common, idempotencyKey: key },
            )
          : await api.acceptOperationalGridGeometryProposal?.(
              item.id,
              proposal.id,
              context,
              {
                ...common,
                expectedGeometryRevision:
                  proposal.candidate.expectedGeometryRevision,
                expectedResolutionRevision:
                  proposal.candidate.expectedResolutionRevision,
                originalCandidateSha256:
                  proposal.candidate.originalCandidateSha256,
                mode: 'model',
                ...(item.manualCropPolicyVersion == null
                  ? {}
                  : { cropPolicyVersion: item.manualCropPolicyVersion }),
                idempotencyKey: key,
              },
            );
      if (result?.data === undefined)
        throw new Error(
          apiErrorMessage(
            result?.error,
            'Propozycja zmieniła się. Odśwież planszę.',
          ),
        );
      // Receipt is historical. Only the fresh current view controls the UI.
      if (result.data.current !== null)
        setData((old) => ({
          candidates:
            old?.candidates.filter(
              (c) =>
                !('targetResultId' in candidate) ||
                c.targetResultId !== candidate.targetResultId,
            ) ?? [],
          proposals: [
            result.data!.current!,
            ...(old?.proposals.filter((p) => p.id !== proposal.id) ?? []),
          ],
        }));
      setMessage(
        action === 'reject'
          ? 'Odrzucono propozycję. Zgłoszenie siatki pozostaje otwarte.'
          : 'Zapisano decyzję. Odświeżono bieżący stan.',
      );
      if (action === 'accept') onChanged();
      else onRejected?.();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Nie udało się zapisać decyzji.',
      );
    } finally {
      setBusy(false);
    }
  }

  const target = useMemo<BoardGeometryCorrectionTarget | null>(() => {
    if (editing === null) return null;
    const proposal = editing;
    const base = operationalBoardGeometryTarget({
      api,
      apiBaseUrl,
      importJobId,
      item,
    });
    const nodes = parseBoardLattice(
      proposal.candidate.originalGeometry.latticeNodes,
    );
    const binding = `${proposal.id}:${proposal.revision}:${item.sourceChecksumSha256}:${item.geometryRevision}:${item.resolutionRevision}:${proposal.candidate.originalCandidateSha256}${item.manualCropPolicyVersion == null ? '' : `:${item.manualCropPolicyVersion}`}`;
    return {
      ...base,
      key: `proposal:${binding}`,
      draftKey: `proposal:${proposal.id}`,
      async load() {
        const loaded = await base.load();
        if (!loaded.ok || nodes === null) return loaded;
        return {
          ok: true,
          view: {
            ...loaded.view,
            draftBindingKey: binding,
            suggestedCorners: boardLatticeTransportCorners(nodes),
            suggestedLatticeNodes: nodes,
            referenceCorners: loaded.view.suggestedCorners,
            supportsLatticeEditing: true,
            suggestionNotice:
              'Propozycja modelu. Zapisz własną korektę, aby ją przyjąć.',
          },
        };
      },
      async save(corners, flags, idempotencyKey, _symbols, latticeNodes) {
        const geometry = JSON.parse(
          base.commandKey(corners, flags, latticeNodes),
        ) as OperationalImageReviewGeometryPreviewCommand;
        geometry.geometryQualification ??=
          proposal.candidate.originalGeometry.geometryQualification;
        const result = await api.acceptOperationalGridGeometryProposal?.(
          item.id,
          proposal.id,
          context,
          {
            idempotencyKey,
            expectedProposalRevision: proposal.revision,
            expectedGeometryRevision: item.geometryRevision,
            expectedResolutionRevision: item.resolutionRevision,
            originalCandidateSha256: proposal.candidate.originalCandidateSha256,
            mode: 'edited',
            ...(item.manualCropPolicyVersion == null
              ? {}
              : { cropPolicyVersion: item.manualCropPolicyVersion }),
            geometry,
          },
        );
        if (result?.data === undefined)
          return {
            ok: false,
            isConflict: result?.response?.status === 409,
            error: apiErrorMessage(
              result?.error,
              'Nie udało się przyjąć korekty. Odśwież planszę.',
            ),
          };
        return { ok: true, reviewItemId: item.id };
      },
    };
  }, [editing, api, apiBaseUrl, importJobId, item, context]);

  if (api.listOperationalGridGeometryProposals === undefined) return null;
  const entries = [...(data?.proposals ?? []), ...(data?.candidates ?? [])];
  if (entries.length === 0 && !message) return null;
  return (
    <section aria-label="Propozycje modelu">
      <h3>Propozycja modelu</h3>
      {message ? <p role="status">{message}</p> : null}
      {entries.map((candidate) => {
        const original =
          'id' in candidate
            ? candidate.candidate.originalGeometry
            : candidate.originalGeometry;
        const pin =
          'id' in candidate
            ? candidate.candidate.modelSnapshot
            : candidate.modelSnapshot;
        const id = 'id' in candidate ? candidate.id : candidate.targetResultId;
        return (
          <details key={id} open>
            <summary>Model {modelLabel(pin)}</summary>
            <p>Aktualna siatka: niebieska. Proponowana siatka: pomarańczowa.</p>
            {candidate.recognitionStatus ? (
              <p>
                Przy przygotowaniu: automat{' '}
                {candidate.recognitionStatus.automatic.state === 'qualified'
                  ? 'miał kwalifikację'
                  : 'wymagał kwalifikacji'}
                . Ratunek: {candidate.recognitionStatus.rescue.state}.{' '}
                {candidate.recognitionStatus.rescue.state === 'foreign_scope'
                  ? 'Próby dotyczą innego zakresu pozycji; nie były wejściem tej planszy.'
                  : null}{' '}
                To propozycja do ręcznej oceny, nie zatwierdzenie człowieka.{' '}
                {candidate.recognitionStatus.reasonCodes.join('; ')}
              </p>
            ) : null}
            <svg
              role="img"
              aria-label="Porównanie obecnej siatki i propozycji"
              viewBox={`0 0 ${item.sourceWidth ?? 1} ${item.sourceHeight ?? 1}`}
              style={{ width: '100%', maxHeight: 360 }}
            >
              <image
                href={operationalReviewAssetUrl(
                  apiBaseUrl,
                  context,
                  item.id,
                  'source',
                  { version: item.sourceChecksumSha256 },
                )}
                width={item.sourceWidth ?? 1}
                height={item.sourceHeight ?? 1}
              />
              {[
                { nodes: item.latticeNodes, color: '#1166ff' },
                { nodes: original.latticeNodes, color: '#ff9900' },
              ].map(({ nodes, color }) =>
                nodes ? (
                  <g key={color} fill="none" stroke={color} strokeWidth={2}>
                    {Array.from({ length: 4 }, (_, r) => (
                      <polyline
                        key={`r${r}`}
                        points={nodes
                          .slice(r * 6, r * 6 + 6)
                          .map((n) => `${n.x},${n.y}`)
                          .join(' ')}
                      />
                    ))}
                    {Array.from({ length: 6 }, (_, c) => (
                      <polyline
                        key={`c${c}`}
                        points={Array.from(
                          { length: 4 },
                          (_, r) => nodes[r * 6 + c],
                        )
                          .map((n) => `${n!.x},${n!.y}`)
                          .join(' ')}
                      />
                    ))}
                  </g>
                ) : null,
              )}
            </svg>
            {!candidate.applicable ? (
              <p>
                Propozycja nie jest obecnie dostępna:{' '}
                {candidate.reasons.join(', ')}. Historia decyzji nie potwierdza
                bieżącej geometrii.
              </p>
            ) : null}
            <div className="geometryViewportControls">
              <button
                className="primaryButton"
                disabled={busy || !candidate.applicable}
                onClick={() => void act(candidate, 'accept')}
              >
                Przyjmij propozycję
              </button>
              <button
                disabled={busy || !candidate.applicable}
                className="secondaryButton"
                onClick={() => void act(candidate, 'edit')}
              >
                Edytuj propozycję
              </button>
              <button
                disabled={
                  busy ||
                  ('state' in candidate && candidate.state !== 'pending')
                }
                className="secondaryButton"
                onClick={() => void act(candidate, 'reject')}
              >
                Odrzuć propozycję
              </button>
            </div>
          </details>
        );
      })}
      <dialog
        ref={dialog}
        onCancel={(event) => {
          event.preventDefault();
          setEditing(null);
        }}
        aria-label="Edytuj propozycję modelu"
      >
        <button className="secondaryButton" onClick={() => setEditing(null)}>
          Zamknij edytor propozycji
        </button>
        {target ? (
          <BoardGeometryCorrectionEditor
            key={target.key}
            target={target}
            viewportControls
            saveLabel="Przyjmij własną korektę"
            onConflict={async (message) =>
              setMessage(`${message} Odśwież planszę; szkic zachowano.`)
            }
            onSaved={async () => {
              setEditing(null);
              onChanged();
            }}
          />
        ) : null}
      </dialog>
    </section>
  );
}
