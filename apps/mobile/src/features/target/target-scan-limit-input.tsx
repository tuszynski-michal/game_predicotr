import {
  TARGET_SCAN_LIMIT_MAX,
  TARGET_SCAN_LIMIT_UI_MIN,
} from '@game-predictor/shared-ts';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { boardColors } from '@/features/board/board-theme';

type Props = {
  onChangeText: (value: string) => void;
  value: string;
};

export function parseTargetScanLimit(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) &&
    parsed >= TARGET_SCAN_LIMIT_UI_MIN &&
    parsed <= TARGET_SCAN_LIMIT_MAX
    ? parsed
    : null;
}

export function TargetScanLimitInput({ onChangeText, value }: Props) {
  const valid = parseTargetScanLimit(value) !== null;

  return (
    <View style={styles.container} testID="target-scan-limit-control">
      <View style={styles.labelGroup}>
        <Text style={styles.label}>Zakres Targetu</Text>
        <Text style={styles.hint}>1 000–500 000 spinów</Text>
      </View>
      <TextInput
        accessibilityLabel="Liczba spinów w obliczeniu Target"
        accessibilityValue={{
          text: valid ? `${value} spinów` : 'Niepoprawna wartość',
        }}
        inputMode="numeric"
        keyboardType="number-pad"
        maxLength={6}
        onChangeText={onChangeText}
        selectTextOnFocus
        style={[styles.input, !valid && styles.inputInvalid]}
        testID="target-scan-limit-input"
        value={value}
      />
      {valid ? null : (
        <Text
          accessibilityLiveRegion="polite"
          style={styles.error}
          testID="target-scan-limit-error"
        >
          Podaj liczbę całkowitą od 1 000 do 500 000.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    backgroundColor: boardColors.card,
    borderColor: boardColors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    minHeight: 54,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  error: {
    color: '#fca5a5',
    flexBasis: '100%',
    fontSize: 11,
    paddingBottom: 3,
  },
  hint: {
    color: boardColors.muted,
    fontSize: 10,
    marginTop: 1,
  },
  input: {
    backgroundColor: '#102640',
    borderColor: boardColors.border,
    borderRadius: 9,
    borderWidth: 1,
    color: boardColors.text,
    fontSize: 15,
    fontVariant: ['tabular-nums'],
    marginLeft: 'auto',
    minHeight: 44,
    minWidth: 112,
    paddingHorizontal: 10,
    paddingVertical: 6,
    textAlign: 'right',
  },
  inputInvalid: {
    borderColor: '#dc2626',
  },
  label: {
    color: boardColors.text,
    fontSize: 12,
    fontWeight: '700',
  },
  labelGroup: {
    flexShrink: 1,
  },
});
