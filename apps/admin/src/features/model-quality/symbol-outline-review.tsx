'use client';

import type { ContentOutlineProposal } from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  OUTLINE_PAGE_SIZE,
  type OutlineSelection,
  type OutlineView,
  outlineApprovalCommand,
  outlineSelectable,
  outlineViewBox,
  selectPage,
  toggleSelection,
} from './symbol-outline-state';

/**
 * D-608: symbol outlines taken from the operator's approved grids. A click on a tile
 * selects it; „Zatwierdź zaznaczone” writes one ordinary approved content label per board.
 */
export function SymbolOutlineReview({
  apiBaseUrl,
  gameId,
}: {
  readonly apiBaseUrl: string;
  readonly gameId: string;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [view, setView] = useState<OutlineView>('todo');
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<{
    key: string;
    items: ContentOutlineProposal[];
    counts: { todo: number; approved: number };
    nextOffset: number | null;
    error: string;
  }>({
    key: '',
    items: [],
    counts: { todo: 0, approved: 0 },
    nextOffset: null,
    error: '',
  });
  const [selected, setSelected] = useState<OutlineSelection>(new Map());
  const [showOutlines, setShowOutlines] = useState(true);
  const [zoomed, setZoomed] = useState<ContentOutlineProposal | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  const requestKey = `${gameId}:${view}:${offset}:${reload}`;
  const loading = page.key !== requestKey;
  const { items, counts, nextOffset } = page;
  useEffect(() => {
    let active = true;
    const failed = (message: string) =>
      setPage((current) => ({ ...current, key: requestKey, error: message }));
    void api
      .listGridContentOutlineProposals(gameId, {
        view,
        offset,
        limit: OUTLINE_PAGE_SIZE,
      })
      .then((result) => {
        if (!active) return;
        if (!result.data) {
          failed('Nie udało się odczytać plansz z zatwierdzonymi siatkami.');
          return;
        }
        setPage({
          key: requestKey,
          items: result.data.items,
          counts: result.data.counts,
          nextOffset: result.data.nextOffset ?? null,
          error: '',
        });
      })
      .catch((failure: unknown) => {
        if (active) failed(String(failure));
      });
    return () => {
      active = false;
    };
  }, [api, gameId, view, offset, reload, requestKey]);

  const toggle = useCallback(
    (item: ContentOutlineProposal) => {
      if (saving || !outlineSelectable(item)) return;
      setSelected((current) => toggleSelection(current, item));
    },
    [saving],
  );

  async function approve() {
    const chosen = [...selected.values()];
    if (
      !chosen.length ||
      !window.confirm(
        `Zatwierdzić obrysy ${chosen.length} plansz? Każda dostanie zatwierdzoną etykietę zawartości.`,
      )
    )
      return;
    setSaving(true);
    setMessage('');
    setError('');
    let ok = 0;
    const failures: string[] = [];
    for (const [index, item] of chosen.entries()) {
      setMessage(`Zapisywanie ${index + 1}/${chosen.length}…`);
      try {
        const result = await api.writeGridCellContentReference(
          gameId,
          outlineApprovalCommand(item, crypto.randomUUID()),
        );
        if (result.data) ok += 1;
        else
          failures.push(
            `plansza ${item.sequenceNumber}: ${JSON.stringify(result.error).slice(0, 160)}`,
          );
      } catch (failure) {
        failures.push(`plansza ${item.sequenceNumber}: ${String(failure)}`);
      }
    }
    setSelected((current) => {
      const next = new Map(current);
      for (const item of chosen) next.delete(item.boardId);
      return next;
    });
    setMessage(`Zatwierdzono ${ok} z ${chosen.length} plansz.`);
    if (failures.length)
      setError(`Nie zapisano ${failures.length}: ${failures.join('; ')}`);
    setSaving(false);
    setReload((value) => value + 1);
  }

  const pageNumber = Math.floor(offset / OUTLINE_PAGE_SIZE) + 1;
  return (
    <section
      className={`symbolOutlineReview${showOutlines ? '' : ' hideOutlines'}`}
      aria-label="Obrysy symboli z siatek"
    >
      <header className="symbolOutlineToolbar">
        <h1>Obrysy symboli z siatek</h1>
        <span>
          Do zatwierdzenia {counts.todo} · zatwierdzone {counts.approved}
        </span>
        <label>
          Pokaż{' '}
          <select
            value={view}
            disabled={saving}
            onChange={(event) => {
              setView(event.target.value as OutlineView);
              setOffset(0);
            }}
          >
            <option value="todo">do zatwierdzenia</option>
            <option value="approved">zatwierdzone</option>
            <option value="all">wszystkie</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={showOutlines}
            onChange={(event) => setShowOutlines(event.target.checked)}
          />{' '}
          obrysy
        </label>
        <button
          type="button"
          className="secondaryButton"
          disabled={saving || loading}
          onClick={() => setSelected((current) => selectPage(current, items))}
        >
          Zaznacz całą stronę
        </button>
        <button
          type="button"
          className="secondaryButton"
          disabled={saving || !selected.size}
          onClick={() => setSelected(new Map())}
        >
          Odznacz wszystko
        </button>
        <button
          type="button"
          className="primaryButton"
          disabled={saving || !selected.size}
          onClick={() => void approve()}
        >
          Zatwierdź zaznaczone ({selected.size})
        </button>
        <span className="symbolOutlinePager">
          <button
            type="button"
            className="secondaryButton"
            aria-label="Poprzednia strona"
            disabled={saving || loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - OUTLINE_PAGE_SIZE))}
          >
            ◀
          </button>
          strona {pageNumber}
          <button
            type="button"
            className="secondaryButton"
            aria-label="Następna strona"
            disabled={saving || loading || nextOffset === null}
            onClick={() => nextOffset !== null && setOffset(nextOffset)}
          >
            ▶
          </button>
        </span>
      </header>
      <p className="symbolOutlineHint">
        Zielone obrysy to pola Twoich zatwierdzonych siatek. Kliknij kafelek
        planszy, na której każdy obrys obejmuje cały symbol bez sąsiada, i
        zatwierdź zaznaczone. Lupa powiększa planszę. Niezaznaczonych nic nie
        zmienia.
      </p>
      {message ? <p role="status">{message}</p> : null}
      {error || page.error ? <p role="alert">{error || page.error}</p> : null}
      {loading && !items.length ? <p>Wczytywanie…</p> : null}
      {!loading && !items.length && !page.error ? (
        <p>Brak plansz w tym widoku.</p>
      ) : null}
      <ul className="symbolOutlineGrid">
        {items.map((item) => {
          const chosen = selected.has(item.boardId);
          const selectable = outlineSelectable(item);
          return (
            <li
              key={item.boardId}
              className={`symbolOutlineTile${chosen ? ' selected' : ''}${item.contentApproved ? ' approved' : ''}`}
            >
              <button
                type="button"
                className="symbolOutlineSelect"
                aria-pressed={chosen}
                disabled={!selectable || saving}
                onClick={() => toggle(item)}
              >
                <OutlineImage
                  item={item}
                  margin={0.12}
                  url={api.imageGeometryCompletenessSourceUrl(
                    gameId,
                    item.source.sourceId,
                  )}
                />
                <span className="symbolOutlineMeta">
                  Plansza {item.sequenceNumber} · pozycja{' '}
                  {item.positionIndex + 1}
                  <strong>
                    {item.contentApproved
                      ? 'zatwierdzone'
                      : item.cells == null
                        ? 'siatka nieużywalna'
                        : chosen
                          ? '✓ obrysy dobre'
                          : ''}
                  </strong>
                </span>
              </button>
              <button
                type="button"
                className="symbolOutlineZoom"
                aria-label={`Powiększ planszę ${item.sequenceNumber}`}
                onClick={() => setZoomed(item)}
              >
                🔍
              </button>
            </li>
          );
        })}
      </ul>
      {zoomed ? (
        <div
          className="symbolOutlineModal"
          role="dialog"
          aria-label={`Plansza ${zoomed.sequenceNumber}`}
          onClick={() => setZoomed(null)}
          onKeyDown={(event) => event.key === 'Escape' && setZoomed(null)}
          tabIndex={-1}
        >
          <OutlineImage
            item={zoomed}
            margin={0.06}
            url={api.imageGeometryCompletenessSourceUrl(
              gameId,
              zoomed.source.sourceId,
            )}
          />
        </div>
      ) : null}
    </section>
  );
}

function OutlineImage({
  item,
  margin,
  url,
}: {
  readonly item: ContentOutlineProposal;
  readonly margin: number;
  readonly url: string;
}) {
  const [x, y, w, h] = outlineViewBox(item, margin);
  const stroke = Math.max(w, h) / 300;
  return (
    <svg
      viewBox={`${x} ${y} ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`Plansza ${item.sequenceNumber} z obrysami`}
    >
      <image
        href={url}
        x={0}
        y={0}
        width={item.source.width}
        height={item.source.height}
      />
      {(item.cells ?? []).map((cell, index) =>
        cell.quad ? (
          <polygon
            key={index}
            points={cell.quad.map((p) => p.join(',')).join(' ')}
            fill="none"
            stroke="#22c55e"
            strokeWidth={stroke}
          />
        ) : null,
      )}
    </svg>
  );
}
