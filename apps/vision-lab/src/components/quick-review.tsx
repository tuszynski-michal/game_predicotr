'use client';
/* eslint-disable @next/next/no-img-element -- registered local source, no optimizer */
import { useEffect, useRef, useState } from 'react';
import {
  assetUrl,
  writePhotoReview,
  type AnnotationState,
  type PhotoReviewRequest,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';
import { useToast } from '../../../../packages/ui/src/toasts';
import { useAnnotations } from './annotation-context';
import {
  boardStatus,
  photoReviewStatus,
  photoVersions,
  sourceAnnotations,
} from '../lib/annotation-status';
import { nextQuickReview, quickReviewQueue } from '../lib/quick-review';

export function QuickReview({
  sources,
  initialState,
  game,
  onReturn,
}: {
  sources: Source[];
  initialState: AnnotationState;
  game: string;
  onReturn: () => void;
}) {
  const { state, accept, refresh } = useAnnotations();
  const notify = useToast();
  const [queue] = useState(() => quickReviewQueue(sources, initialState, game));
  const [cursor, setCursor] = useState(0);
  const [view, setView] = useState(initialState);
  const [epoch, setEpoch] = useState(0);
  const [loaded, setLoaded] = useState('');
  const [pending, setPending] = useState<PhotoReviewRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const alive = useRef(true);
  const latest = useRef(initialState);
  useEffect(() => {
    if (state && state.revision >= latest.current.revision)
      latest.current = state;
  }, [state]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const source = queue[cursor];
  const rows = source ? sourceAnnotations(view, source.id) : [];
  const imageKey = `${source?.id}:${cursor}:${epoch}`;
  const ready = !!source && loaded === imageKey;
  const blocked = busy || !!pending;
  function show(next: AnnotationState, start: number) {
    setView(next);
    setCursor(nextQuickReview(queue, next, start));
    setEpoch((value) => value + 1);
    setLoaded('');
  }
  async function decide(action: 'accept' | 'reject', retry = false) {
    if (!source || locked.current || (!retry && (pending || !ready))) return;
    const body = pending ?? {
      request_id: crypto.randomUUID(),
      expected_revision: view.revision,
      actor: 'operator',
      action,
      source_id: source.id,
      source_sha256: source.sha256,
      expected_board_revisions: photoVersions(rows),
      board_indices: [],
      note: '',
    };
    locked.current = true;
    setBusy(true);
    setPending(body);
    try {
      const next = await writePhotoReview(body);
      if (!alive.current) return;
      if (next.revision < latest.current.revision)
        throw new Error('Stale response');
      accept(next);
      latest.current = next;
      const review = next.photo_reviews?.[source.id];
      const currentRows = sourceAnnotations(next, source.id);
      const versions = photoVersions(currentRows);
      const sameVersions =
        Object.keys(versions).length ===
          Object.keys(body.expected_board_revisions).length &&
        Object.entries(versions).every(
          ([index, revision]) =>
            body.expected_board_revisions[index] === revision,
        );
      if (
        !sameVersions ||
        (body.action === 'reject'
          ? !review?.rejected
          : photoReviewStatus(currentRows, review, source.sha256).status !==
            'accepted')
      )
        throw new Error('Decision no longer current');
      setPending(null);
      show(next, cursor + 1);
      notify({
        kind: 'success',
        message:
          body.action === 'accept'
            ? 'Zdjęcie zatwierdzone.'
            : 'Zdjęcie odrzucone — Do poprawy.',
      });
    } catch {
      if (alive.current)
        notify({
          kind: 'error',
          message:
            'Decyzja niepotwierdzona lub stan zmienił się. Ponów identyczne żądanie albo odśwież i sprawdź zdjęcie.',
        });
    } finally {
      locked.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function reconcile() {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    try {
      const next = await refresh();
      if (!alive.current) return;
      if (next.revision < latest.current.revision)
        throw new Error('Stale read');
      latest.current = next;
      setPending(null);
      show(next, cursor);
      notify({
        kind: 'info',
        message:
          'Odczytano aktualny stan. Sprawdź wyświetlone siatki przed decyzją.',
      });
    } catch {
      if (alive.current)
        notify({
          kind: 'error',
          message:
            'Nie udało się odświeżyć. Niepotwierdzone żądanie pozostaje do ponowienia.',
        });
    } finally {
      locked.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return (
    <main className="quick-review" aria-label="Szybki przegląd">
      <header className="quick-review-header">
        <h1>Szybki przegląd</h1>
        <span>
          {source
            ? `Zdjęcie ${cursor + 1} z ${queue.length}`
            : `Koniec kolejki (${queue.length} zdjęć)`}
        </span>
        <button
          disabled={blocked}
          onClick={() => {
            if (!locked.current && !pending) onReturn();
          }}
        >
          Powrót do edycji
        </button>
      </header>
      {source ? (
        <>
          <QuickReviewPhoto
            key={imageKey}
            source={source}
            rows={rows}
            onLoaded={() => setLoaded(imageKey)}
            onError={() => {
              setLoaded('');
              notify({
                kind: 'error',
                message:
                  'Nie można wczytać zdjęcia. Odśwież przed podjęciem decyzji.',
              });
            }}
          />
          <footer className="quick-review-actions">
            <button
              className="quick-accept"
              disabled={!ready || blocked}
              onClick={(event) => {
                if (event.detail <= 1) void decide('accept');
              }}
            >
              Zatwierdź
            </button>
            <button
              className="quick-reject"
              disabled={!ready || blocked}
              onClick={(event) => {
                if (event.detail <= 1) void decide('reject');
              }}
            >
              Odrzuć
            </button>
            {pending && (
              <button
                disabled={busy}
                onClick={() =>
                  decide(pending.action as 'accept' | 'reject', true)
                }
              >
                Ponów identyczną decyzję
              </button>
            )}
            {(pending || !ready) && (
              <button disabled={busy} onClick={reconcile}>
                Odśwież zdjęcie i stan
              </button>
            )}
          </footer>
        </>
      ) : (
        <p className="quick-review-complete">
          Wszystkie zdjęcia z tej kolejki są rozstrzygnięte. Poprawki znajdziesz
          w filtrze „Do poprawy”.
        </p>
      )}
    </main>
  );
}

function QuickReviewPhoto({
  source,
  rows,
  onLoaded,
  onError,
}: {
  source: Source;
  rows: ReturnType<typeof sourceAnnotations>;
  onLoaded: () => void;
  onError: () => void;
}) {
  const [size, setSize] = useState({ width: 1, height: 1 });
  return (
    <div className="quick-review-photo">
      <img
        className="quick-source-loader"
        hidden
        src={assetUrl(source.asset_id)}
        alt=""
        onLoad={(event) => {
          const { naturalWidth: width, naturalHeight: height } =
            event.currentTarget;
          if (width < 1 || height < 1) {
            onError();
            return;
          }
          setSize({ width, height });
        }}
        onError={onError}
      />
      <svg
        viewBox={`0 0 ${size.width} ${size.height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Całe zdjęcie ze wszystkimi zapisanymi siatkami"
      >
        {size.width > 1 && (
          <image
            href={assetUrl(source.asset_id)}
            width={size.width}
            height={size.height}
            onLoad={onLoaded}
            onError={onError}
          />
        )}
        {rows
          .filter((row) => row.corners.length === 4)
          .map((row) => (
            <g
              key={row.board_index}
              aria-label={`Plansza ${row.board_index + 1}`}
            >
              <polygon
                points={row.corners.map((p) => `${p.x},${p.y}`).join(' ')}
                fill="none"
                stroke={boardStatus(row) === 'full' ? '#74dcba' : '#ffce54'}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
              {Array.from({ length: 4 }, (_, i) => (
                <polyline
                  key={`r${i}`}
                  points={row.nodes
                    .slice(
                      i * (row.topology.columns + 1),
                      (i + 1) * (row.topology.columns + 1),
                    )
                    .map((p) => `${p.x},${p.y}`)
                    .join(' ')}
                  fill="none"
                  stroke="#fff"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {Array.from({ length: row.topology.columns + 1 }, (_, i) => (
                <polyline
                  key={`c${i}`}
                  points={row.nodes
                    .filter((_, n) => n % (row.topology.columns + 1) === i)
                    .map((p) => `${p.x},${p.y}`)
                    .join(' ')}
                  fill="none"
                  stroke="#fff"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              <text
                x={row.corners[0].x}
                y={row.corners[0].y + size.width / 35}
                fontSize={size.width / 35}
                fill="#fff"
                stroke="#101827"
                strokeWidth={size.width / 700}
                paintOrder="stroke"
              >
                {row.board_index + 1}
              </text>
            </g>
          ))}
      </svg>
    </div>
  );
}
