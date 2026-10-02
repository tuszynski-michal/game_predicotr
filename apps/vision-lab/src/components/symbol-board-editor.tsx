'use client';
/* eslint-disable @next/next/no-img-element -- exact protected preview bytes */
import { useEffect, useRef, useState } from 'react';
import {
  symbolBoard,
  type AnnotationState,
  type LabBoardPreview,
  type Source,
  type SymbolRequest,
} from '../../../../packages/vision-lab-api-client/src/index';
import {
  boardChoices,
  boardDecision,
  boardImagesReady,
  boardOverlay,
  boardReadSession,
} from '../lib/symbol-board-workflow';

type Props = {
  game: string;
  sources: Source[];
  annotations: AnnotationState | null;
  revision: number;
  readVersion: number;
  disabled: boolean;
  onBusy: (value: boolean) => void;
  onSubmit: (body: SymbolRequest) => Promise<void>;
  onError: (message: string) => void;
};

export function SymbolBoardEditor({
  game,
  sources,
  annotations,
  revision,
  readVersion,
  disabled,
  onBusy,
  onSubmit,
  onError,
}: Props) {
  const [sourceId, setSourceId] = useState('');
  const [boardIndex, setBoardIndex] = useState<number | null>(null);
  const [preview, setPreview] = useState<LabBoardPreview | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [previewSession, setPreviewSession] = useState(0);
  const readSession = useRef(boardReadSession());
  const imageErrorSession = useRef<number | null>(null);
  const available = Object.values(annotations?.annotations ?? {}).filter(
    (a) => a.full_approved && a.presence === 'present',
  );
  const sourceOptions = sources.filter(
    (s) => s.game_id === game && available.some((a) => a.source_id === s.id),
  );
  const boards = available
    .filter((a) => a.source_id === sourceId)
    .sort((a, b) => a.board_index - b.board_index);
  const geometryRevision = boards.find(
    (a) => a.board_index === boardIndex,
  )?.revision;

  useEffect(() => {
    const session = readSession.current;
    const current = session.begin();
    let disposed = false;
    if (!sourceId || boardIndex === null || !geometryRevision) {
      void Promise.resolve().then(() => {
        if (disposed || !session.isCurrent(current)) return;
        setPreview(null);
        setChoices([]);
        setLoaded(new Set());
        setFailed(false);
      });
      return () => {
        disposed = true;
        session.invalidate();
      };
    }
    onBusy(true);
    void Promise.resolve()
      .then(() => {
        if (disposed || !session.isCurrent(current)) return null;
        setPreview(null);
        setChoices([]);
        setLoaded(new Set());
        setFailed(false);
        return symbolBoard({
          kind: 'lab_board',
          source_id: sourceId,
          board_index: boardIndex,
          expected_geometry_revision: geometryRevision,
        });
      })
      .then((value) => {
        if (!value || disposed || !session.isCurrent(current)) return;
        setPreviewSession(current);
        setPreview(value);
        setChoices(boardChoices(value));
        setLoaded(new Set());
        setFailed(false);
      })
      .catch((error: unknown) => {
        if (!disposed && session.isCurrent(current))
          onError(`Podgląd planszy niedostępny: ${errorMessage(error)}`);
      })
      .finally(() => {
        if (!disposed && session.isCurrent(current)) onBusy(false);
      });
    return () => {
      disposed = true;
      session.invalidate();
      onBusy(false);
    };
  }, [
    sourceId,
    boardIndex,
    geometryRevision,
    annotations?.revision,
    revision,
    readVersion,
    reload,
    onBusy,
    onError,
  ]);

  function clear() {
    readSession.current.invalidate();
    setPreview(null);
    setChoices([]);
    setLoaded(new Set());
    setFailed(false);
  }
  function imageLoaded(key: string, session: number) {
    if (readSession.current.isCurrent(session))
      setLoaded((previous) => new Set([...previous, key]));
  }
  function imageFailed(session: number) {
    if (!readSession.current.isCurrent(session)) return;
    setFailed(true);
    if (imageErrorSession.current !== session) {
      imageErrorSession.current = session;
      onError(
        'Nie udało się wczytać obrazu. Odczytaj planszę ponownie przed zapisem.',
      );
    }
  }
  const overlay = preview ? boardOverlay(preview) : null;
  const ready = preview && boardImagesReady(preview, loaded, failed);
  return (
    <fieldset disabled={disabled || !game} className="symbol-board-editor">
      <legend>Symbole całej planszy</legend>
      <label>
        Zdjęcie{' '}
        <select
          value={sourceId}
          onChange={(e) => {
            clear();
            setSourceId(e.target.value);
            setBoardIndex(
              available
                .filter((a) => a.source_id === e.target.value)
                .sort((a, b) => a.board_index - b.board_index)[0]
                ?.board_index ?? null,
            );
          }}
        >
          <option value="">Wybierz zdjęcie</option>
          {sourceOptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.filename}
            </option>
          ))}
        </select>
      </label>
      <label>
        Plansza{' '}
        <select
          value={boardIndex ?? ''}
          disabled={!sourceId}
          onChange={(e) => {
            clear();
            setBoardIndex(Number(e.target.value));
          }}
        >
          {boardIndex === null && <option value="">Wybierz planszę</option>}
          {boards.map((a) => (
            <option key={a.board_index} value={a.board_index}>
              Plansza {a.board_index + 1}
            </option>
          ))}
        </select>
      </label>
      {!sourceOptions.length && (
        <p>
          Brak zapisanej pełnej geometrii dla tej gry. Zatwierdź planszę w
          widoku geometrii.
        </p>
      )}
      {sourceId && (
        <button
          onClick={() => {
            clear();
            setReload((v) => v + 1);
          }}
        >
          Odczytaj planszę ponownie
        </button>
      )}
      {preview && overlay && (
        <div key={previewSession} className="symbol-board-content">
          <div className="symbol-board-picture">
            <img
              src={`data:image/png;base64,${preview.board_png_base64}`}
              width={preview.width}
              height={preview.height}
              alt="Cała plansza z siatką i numerami pól"
              onLoad={() => imageLoaded('board', previewSession)}
              onError={() => imageFailed(previewSession)}
            />
            <svg
              viewBox={`0 0 ${preview.width} ${preview.height}`}
              aria-hidden="true"
            >
              {overlay.lines.map((points, index) => (
                <polyline key={index} points={points} />
              ))}
              {overlay.labels.map((p) => (
                <text
                  key={p.index}
                  x={p.x}
                  y={p.y}
                  style={{
                    fontSize: (14 * preview.width) / 640,
                    strokeWidth: (3 * preview.width) / 640,
                  }}
                >
                  {p.index + 1}
                </text>
              ))}
            </svg>
          </div>
          <div
            className="symbol-board-cells"
            style={{
              gridTemplateColumns: `repeat(${preview.topology.columns}, minmax(0, 1fr))`,
            }}
          >
            {preview.cells.map((cell, index) => (
              <label key={cell.binding.crop_id} className="symbol-board-cell">
                <span>Pole {cell.binding.cell_index + 1}</span>
                <img
                  src={`data:image/png;base64,${cell.png_base64}`}
                  width={96}
                  height={96}
                  alt={`Dokładny crop pola ${cell.binding.cell_index + 1}`}
                  onLoad={() =>
                    imageLoaded(String(cell.binding.cell_index), previewSession)
                  }
                  onError={() => imageFailed(previewSession)}
                />
                <select
                  aria-label={`Symbol pola ${cell.binding.cell_index + 1}`}
                  value={choices[index] ?? ''}
                  disabled={!preview.dictionary}
                  onChange={(e) =>
                    setChoices(
                      choices.map((v, i) => (i === index ? e.target.value : v)),
                    )
                  }
                >
                  <option value="">Wybierz</option>
                  {preview.dictionary?.entries?.map((entry) => (
                    <option key={entry.id} value={`class:${entry.id}`}>
                      {entry.display_name}
                    </option>
                  ))}
                  <option value="state:unknown">Nieznany</option>
                  <option value="state:unreadable">Nieczytelne</option>
                  <option value="state:grid_issue">Błąd siatki</option>
                </select>
              </label>
            ))}
          </div>
          {!preview.dictionary && (
            <p>Najpierw zapisz i zatwierdź słownik tej gry.</p>
          )}
          {!failed && !ready && <p>Wczytywanie obrazów planszy…</p>}
          <button
            disabled={true}
            onClick={() => {
              try {
                void onSubmit(
                  boardDecision(preview, choices, crypto.randomUUID()),
                );
              } catch (error) {
                onError(errorMessage(error));
              }
            }}
          >
            Zapisz wszystkie {preview.cells.length} pól
          </button>
        </div>
      )}
    </fieldset>
  );
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null && 'detail' in error)
    return String(error.detail);
  return String(error);
}
