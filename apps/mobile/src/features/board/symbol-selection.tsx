import type { SymbolDefinition } from '@game-predictor/shared-ts';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { boardColors } from './board-theme';
import { resolveSymbolAsset } from './symbol-assets';

type Props = {
  disabled: boolean;
  onSelectSymbol: (mobileCode: number) => void;
  symbols: readonly SymbolDefinition[];
};

function normalizedLabel(value: string | undefined): string | null {
  const normalized = value?.trim() ?? '';
  return normalized.length === 0 ? null : normalized;
}

export function selectSymbolLabel(symbol: SymbolDefinition): string {
  const polish = normalizedLabel(symbol.namePl);
  const english = normalizedLabel(symbol.nameEn);
  if (polish !== null && english !== null) {
    return polish.length <= english.length ? polish : english;
  }
  return polish ?? english ?? symbol.name;
}

export function SymbolSelection({ disabled, onSelectSymbol, symbols }: Props) {
  return (
    <View accessibilityLabel="Wybór symbolu" style={styles.list}>
      {symbols.map((symbol) => {
        const imageSource = resolveSymbolAsset(symbol.imageAssetKey);
        const label = selectSymbolLabel(symbol);
        return (
          <Pressable
            accessibilityLabel={`${label}${symbol.isWildcard ? ', joker' : ''}`}
            accessibilityRole="button"
            accessibilityState={{ disabled }}
            disabled={disabled}
            key={symbol.mobileCode}
            onPress={() => onSelectSymbol(symbol.mobileCode)}
            style={({ pressed }) => [
              styles.symbol,
              symbol.isWildcard && styles.jokerSymbol,
              disabled && styles.symbolDisabled,
              pressed && !disabled && styles.symbolPressed,
            ]}
            testID={`symbol-${symbol.mobileCode}`}
          >
            {symbol.isWildcard ? (
              <View
                accessibilityElementsHidden
                importantForAccessibility="no-hide-descendants"
                style={styles.jokerMark}
              />
            ) : null}
            {imageSource === null ? null : (
              <Image
                accessibilityIgnoresInvertColors
                source={imageSource}
                style={styles.symbolImage}
              />
            )}
            <Text
              ellipsizeMode="tail"
              numberOfLines={1}
              style={styles.symbolName}
            >
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  jokerMark: {
    backgroundColor: '#a78bfa',
    borderRadius: 4,
    height: 8,
    position: 'absolute',
    right: 5,
    top: 5,
    width: 8,
  },
  jokerSymbol: {
    borderColor: '#a78bfa',
  },
  list: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    width: '100%',
  },
  symbol: {
    alignItems: 'center',
    backgroundColor: '#18304d',
    borderColor: boardColors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: '21%',
    flexGrow: 1,
    justifyContent: 'center',
    maxWidth: '24%',
    minHeight: 68,
    minWidth: 68,
    padding: 6,
  },
  symbolDisabled: {
    opacity: 0.42,
  },
  symbolImage: {
    borderRadius: 7,
    height: 40,
    marginBottom: 4,
    width: 40,
  },
  symbolName: {
    color: boardColors.muted,
    fontSize: 10,
    maxWidth: '100%',
  },
  symbolPressed: {
    backgroundColor: boardColors.accentPressed,
    borderColor: boardColors.accent,
  },
});
