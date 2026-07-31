import type { SymbolDefinition } from '@game-predictor/shared-ts';
import { Image, StyleSheet, Text, View } from 'react-native';

import type { BoardCell } from './board-reducer';
import { boardColors } from './board-theme';
import { resolveSymbolAsset } from './symbol-assets';

type Props = {
  cells: readonly BoardCell[];
  columns: number;
  rows: number;
  symbols: readonly SymbolDefinition[];
};

export function BoardGrid({ cells, columns, rows, symbols }: Props) {
  const symbolByCode = new Map(
    symbols.map((symbol) => [symbol.mobileCode, symbol]),
  );

  return (
    <View
      accessibilityLabel={`Plansza, ${rows} wiersze i ${columns} kolumn`}
      style={styles.grid}
      testID="board-grid"
    >
      {Array.from({ length: rows }, (_, rowIndex) => (
        <View key={`row-${rowIndex}`} style={styles.row}>
          {Array.from({ length: columns }, (_, columnIndex) => {
            const cellIndex = rowIndex * columns + columnIndex;
            const mobileCode = cells[cellIndex] ?? null;
            const symbol =
              mobileCode === null ? undefined : symbolByCode.get(mobileCode);
            const imageSource = resolveSymbolAsset(symbol?.imageAssetKey);
            const label =
              mobileCode === null
                ? `Puste pole, wiersz ${rowIndex + 1}, kolumna ${columnIndex + 1}`
                : `${symbol?.name ?? `Symbol ${mobileCode}`}, wiersz ${rowIndex + 1}, kolumna ${columnIndex + 1}`;

            return (
              <View
                accessibilityLabel={label}
                key={cellIndex}
                style={[
                  styles.cell,
                  mobileCode === null ? styles.emptyCell : styles.filledCell,
                ]}
                testID={`board-cell-${cellIndex}`}
              >
                {imageSource === null ? null : (
                  <Image
                    accessibilityIgnoresInvertColors
                    source={imageSource}
                    style={styles.symbolImage}
                  />
                )}
                <Text
                  style={[
                    styles.cellText,
                    mobileCode === null
                      ? styles.emptyCellText
                      : styles.filledCellText,
                  ]}
                >
                  {mobileCode === null
                    ? '—'
                    : (symbol?.code ?? `S${mobileCode}`)}
                </Text>
                {symbol?.isWildcard === true ? (
                  <Text style={styles.jokerLabel}>JOKER</Text>
                ) : null}
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  cell: {
    alignItems: 'center',
    aspectRatio: 0.88,
    borderRadius: 12,
    flex: 1,
    justifyContent: 'center',
    minWidth: 0,
    paddingHorizontal: 2,
  },
  cellText: {
    fontSize: 14,
    fontWeight: '800',
  },
  emptyCell: {
    backgroundColor: boardColors.cellEmpty,
    borderColor: boardColors.border,
    borderWidth: 1,
  },
  emptyCellText: {
    color: boardColors.muted,
  },
  filledCell: {
    backgroundColor: boardColors.cellFilled,
    borderColor: '#cbd5e1',
    borderWidth: 1,
  },
  filledCellText: {
    color: boardColors.textDark,
  },
  grid: {
    gap: 8,
  },
  jokerLabel: {
    color: boardColors.joker,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.4,
    marginTop: 3,
  },
  row: {
    flexDirection: 'row',
    gap: 8,
  },
  symbolImage: {
    borderRadius: 6,
    height: 34,
    marginBottom: 2,
    width: 34,
  },
});
