import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { boardColors } from '@/features/board/board-theme';

import type { TargetForecastState } from './use-target-forecast';

type Props = {
  onRetry: () => void;
  state: TargetForecastState;
};

export function TargetSummaryCard({ onRetry, state }: Props) {
  if (state.status === 'loading') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.card}
        testID="target-loading"
      >
        <ActivityIndicator color={boardColors.primary} size="small" />
        <Text style={styles.loadingTitle}>
          Obliczanie pełnego cyklu Target…
        </Text>
        <Text style={styles.muted}>
          Odczytujemy kolejne layouty po spinie 0.
        </Text>
      </View>
    );
  }

  if (state.status === 'error') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.errorCard]}
        testID="target-error"
      >
        <Text style={styles.errorTitle}>Nie udało się obliczyć Target</Text>
        <Text style={styles.errorCode}>{state.error.code}</Text>
        <Text style={styles.errorText}>{state.error.message}</Text>
        <Pressable
          accessibilityLabel="Ponów obliczenie Target"
          accessibilityRole="button"
          onPress={onRetry}
          style={styles.retryButton}
          testID="target-retry-button"
        >
          <Text style={styles.retryText}>Ponów obliczenie</Text>
        </Pressable>
      </View>
    );
  }

  if (state.status !== 'ready' || state.result === null) {
    return null;
  }

  const result = state.result;

  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.card, styles.readyCard]}
      testID="target-ready"
    >
      <Text style={styles.readyTitle}>Target obliczony</Text>
      <View style={styles.summaryGrid}>
        <SummaryValue
          label="Ocenione spiny"
          testID="target-evaluated-spin-count"
          value={result.evaluatedSpinCount}
        />
        <SummaryValue
          label="Koszt spinu"
          testID="target-spin-cost"
          value={result.spinCost}
        />
        <SummaryValue
          label="Łączny payout"
          testID="target-final-payout"
          value={result.finalCumulativePayout}
        />
        <SummaryValue
          label="Łączny koszt"
          testID="target-final-cost"
          value={result.finalCumulativeCost}
        />
        <SummaryValue
          label="Wynik końcowy"
          testID="target-final-net"
          value={result.finalNetCredits}
        />
        <SummaryValue
          label="Dodatnie szczyty"
          testID="target-peak-count"
          value={result.positiveLocalPeaks.length}
        />
      </View>
      <Text style={styles.muted}>
        Szczegółowa tabela szczytów zostanie dołączona w następnym zadaniu.
      </Text>
    </View>
  );
}

type SummaryValueProps = {
  label: string;
  testID: string;
  value: number;
};

function SummaryValue({ label, testID, value }: SummaryValueProps) {
  return (
    <View style={styles.summaryItem} testID={testID}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: 'flex-start',
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    minHeight: 90,
    padding: 15,
  },
  errorCard: {
    backgroundColor: '#3b1720',
    borderColor: '#b91c1c',
  },
  errorCode: {
    color: '#fca5a5',
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 5,
  },
  errorText: {
    color: '#fecaca',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 5,
  },
  errorTitle: {
    color: '#fff1f2',
    fontSize: 15,
    fontWeight: '900',
  },
  loadingTitle: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '800',
    marginTop: 9,
  },
  muted: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 9,
  },
  readyCard: {
    backgroundColor: '#0d2f26',
    borderColor: '#15803d',
  },
  readyTitle: {
    color: '#86efac',
    fontSize: 16,
    fontWeight: '900',
  },
  retryButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: '#7f1d1d',
    borderColor: '#fca5a5',
    borderRadius: 12,
    borderWidth: 1,
    minHeight: 48,
    justifyContent: 'center',
    marginTop: 14,
    paddingHorizontal: 16,
  },
  retryText: {
    color: '#fff1f2',
    fontSize: 14,
    fontWeight: '900',
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -4,
    marginTop: 8,
  },
  summaryItem: {
    backgroundColor: '#0b241e',
    borderRadius: 10,
    margin: 4,
    minWidth: '45%',
    padding: 10,
  },
  summaryLabel: {
    color: boardColors.muted,
    fontSize: 11,
  },
  summaryValue: {
    color: boardColors.text,
    fontSize: 18,
    fontWeight: '900',
    marginTop: 3,
  },
});
