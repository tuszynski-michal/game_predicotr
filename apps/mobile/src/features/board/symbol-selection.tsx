import type { SymbolDefinition } from '@game-predictor/shared-ts';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { boardColors } from './board-theme';

type Props = {
  disabled: boolean;
  onSelectSymbol: (mobileCode: number) => void;
  symbols: readonly SymbolDefinition[];
};

export function SymbolSelection({ disabled, onSelectSymbol, symbols }: Props) {
  return (
    <View>
      <View style={styles.headingRow}>
        <Text accessibilityRole="header" style={styles.heading}>
          Selection
        </Text>
        <Text style={styles.hint}>
          {disabled ? 'Plansza jest pełna' : 'Wybierz kolejny symbol'}
        </Text>
      </View>
      <ScrollView
        accessibilityLabel="Wybór symbolu"
        contentContainerStyle={styles.list}
        horizontal
        showsHorizontalScrollIndicator={false}
      >
        {symbols.map((symbol) => (
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
            <Text style={styles.symbolCode}>{symbol.code}</Text>
            <Text numberOfLines={1} style={styles.symbolName}>
              {symbol.name}
            </Text>
            {symbol.isWildcard ? (
              <Text style={styles.jokerText}>JOKER</Text>
            ) : null}
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    color: boardColors.text,
    fontSize: 20,
    fontWeight: '800',
  },
  headingRow: {
    alignItems: 'baseline',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  hint: {
    color: boardColors.muted,
    fontSize: 12,
  },
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
    fontSize: 18,
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
  symbolPressed: {
    backgroundColor: boardColors.accentPressed,
    borderColor: boardColors.accent,
  },
});
