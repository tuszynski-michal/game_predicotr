'use client';

import type { SymbolCellReviewListItemResponse } from '@game-predictor/admin-api-client';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { ReactNode } from 'react';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import {
  SYMBOL_REVIEW_CARD_SIZE,
  SYMBOL_REVIEW_GRID_GAP,
  SYMBOL_REVIEW_ROW_HEIGHT,
  SYMBOL_REVIEW_VIRTUAL_OVERSCAN_ROWS,
} from './symbol-review-virtual-window.ts';
import styles from './symbol-review-virtual-grid.module.css';

interface SymbolReviewVirtualGridProps {
  readonly items: readonly SymbolCellReviewListItemResponse[];
  readonly onVisibleItemsChange: (
    items: readonly SymbolCellReviewListItemResponse[],
  ) => void;
  readonly pageNumber: number;
  readonly renderCard: (item: SymbolCellReviewListItemResponse) => ReactNode;
  readonly scopeKey: string;
}

export function SymbolReviewVirtualGrid({
  items,
  onVisibleItemsChange,
  pageNumber,
  renderCard,
  scopeKey,
}: SymbolReviewVirtualGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const visibleItemIdsRef = useRef('');
  const pageScrollTopsRef = useRef<Readonly<Record<number, number>>>({});
  const [columnCount, setColumnCount] = useState(1);
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack owns measured DOM state.
  const virtualizer = useVirtualizer({
    count: Math.ceil(items.length / columnCount),
    estimateSize: () => SYMBOL_REVIEW_ROW_HEIGHT,
    getScrollElement: () => scrollRef.current,
    overscan: SYMBOL_REVIEW_VIRTUAL_OVERSCAN_ROWS,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const visibleItems = useMemo(
    () =>
      virtualRows.flatMap((row) =>
        items.slice(row.index * columnCount, (row.index + 1) * columnCount),
      ),
    [columnCount, items, virtualRows],
  );

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (element === null) return;
    const updateColumns = () => {
      const availableWidth = Math.max(1, element.clientWidth - 16);
      setColumnCount(
        Math.max(
          1,
          Math.floor(
            (availableWidth + SYMBOL_REVIEW_GRID_GAP) /
              (SYMBOL_REVIEW_CARD_SIZE + SYMBOL_REVIEW_GRID_GAP),
          ),
        ),
      );
    };
    updateColumns();
    const observer = new ResizeObserver(updateColumns);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    pageScrollTopsRef.current = {};
  }, [scopeKey]);

  useLayoutEffect(() => {
    virtualizer.scrollToOffset(pageScrollTopsRef.current[pageNumber] ?? 0, {
      align: 'start',
    });
  }, [pageNumber, scopeKey, virtualizer]);

  useEffect(() => {
    const visibleItemIds = visibleItems.map((item) => item.id).join(',');
    if (visibleItemIds === visibleItemIdsRef.current) return;
    visibleItemIdsRef.current = visibleItemIds;
    onVisibleItemsChange(visibleItems);
  }, [onVisibleItemsChange, visibleItems]);

  return (
    <div
      aria-label="Wirtualizowana lista cropów symboli"
      className={styles.scroller}
      onScroll={(event) => {
        pageScrollTopsRef.current = {
          ...pageScrollTopsRef.current,
          [pageNumber]: event.currentTarget.scrollTop,
        };
      }}
      ref={scrollRef}
    >
      <div
        className={styles.content}
        style={{ height: virtualizer.getTotalSize() }}
      >
        {virtualRows.map((row) => (
          <div
            className={styles.row}
            key={row.key}
            style={{
              gridTemplateColumns: `repeat(${columnCount}, ${SYMBOL_REVIEW_CARD_SIZE}px)`,
              height: row.size,
              transform: `translateY(${row.start}px)`,
            }}
          >
            {items
              .slice(row.index * columnCount, (row.index + 1) * columnCount)
              .map((item) => renderCard(item))}
          </div>
        ))}
      </div>
    </div>
  );
}
