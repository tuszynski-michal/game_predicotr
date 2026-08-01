import type { SymbolDefinition } from '@game-predictor/shared-ts';
import { Image, Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { boardColors } from './board-theme';
import { resolveSymbolAsset } from './symbol-assets';

type Props = {
  disabled: boolean;
  onSelectSymbol: (mobileCode: number) => void;
  symbols: readonly SymbolDefinition[];
};

export function SymbolSelection({ disabled, onSelectSymbol, symbols }: Props) {
  return (
    <ScrollView
      accessibilityLabel="Wybór symbolu"
      contentContainerStyle={styles.list}
      horizontal
      showsHorizontalScrollIndicator={false}
    >
      {symbols.map((symbol) => {
        const imageSource = resolveSymbolAsset(symbol.imageAssetKey);
        return (
          <Pressable
            accessibilityLabel={`${symbol.name}${symbol.isWildcard ? ', joker' : ''}`}
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
            {imageSource === null ? null : (
              <Image
                accessibilityIgnoresInvertColors
                source={imageSource}
                style={styles.symbolImage}
              />
            )}
            <Text style={styles.symbolCode}>{symbol.code}</Text>
            <Text numberOfLines={1} style={styles.symbolName}>
              {symbol.name}
            </Text>
            {symbol.isWildcard ? (
              <Text style={styles.jokerText}>JOKER</Text>
            ) : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  jokerSymbol: {
    borderColor: '#a78bfa',
  },
  jokerText: {
    color: '#ddd6fe',
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.5,
    marginTop: 4,
  },
  list: {
    gap: 10,
    paddingRight: 18,
  },
  symbol: {
    alignItems: 'center',
    backgroundColor: '#18304d',
    borderColor: boardColors.border,
    borderRadius: 14,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 82,
    minWidth: 82,
    padding: 9,
  },
  symbolCode: {
    color: boardColors.text,
    fontSize: 12,
    fontWeight: '900',
  },
  symbolDisabled: {
    opacity: 0.42,
  },
  symbolName: {
    color: boardColors.muted,
    fontSize: 10,
    marginTop: 4,
    maxWidth: 70,
  },
  symbolImage: {
    borderRadius: 8,
    height: 44,
    marginBottom: 5,
    width: 44,
  },
  symbolPressed: {
    backgroundColor: boardColors.accentPressed,
    borderColor: boardColors.accent,
  },
});
