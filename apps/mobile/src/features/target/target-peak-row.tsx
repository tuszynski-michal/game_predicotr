import type { ForecastPeak } from '@game-predictor/shared-ts';
import { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { boardColors } from '@/features/board/board-theme';

type Props = {
  peak: ForecastPeak;
};

export function targetPeakKey(peak: ForecastPeak): string {
  return `${peak.spinNumber}:${peak.sequenceNumber}`;
}

export const TargetPeakRow = memo(function TargetPeakRow({ peak }: Props) {
  const accessibilityLabel = [
    `Dodatni lokalny szczyt na spinie ${peak.spinNumber}`,
    `layout ${peak.sequenceNumber}`,
    `payout spinu ${peak.spinPayout}`,
    `skumulowany payout ${peak.cumulativePayout}`,
    `skumulowany koszt ${peak.cumulativeCost}`,
    `wynik netto ${peak.netCredits}`,
  ].join(', ');

  return (
    <View
      accessible
      accessibilityLabel={accessibilityLabel}
      style={styles.card}
      testID={`target-peak-row-${peak.spinNumber}`}
    >
      <View style={styles.titleRow}>
        <Text style={styles.title}>Dodatni lokalny szczyt</Text>
        <Text style={styles.net}>+{peak.netCredits}</Text>
      </View>
      <View style={styles.grid}>
        <PeakValue label="Spin" value={peak.spinNumber} />
        <PeakValue label="Layout" value={peak.sequenceNumber} />
        <PeakValue label="Payout spinu" value={peak.spinPayout} />
        <PeakValue label="Payout łącznie" value={peak.cumulativePayout} />
        <PeakValue label="Koszt łącznie" value={peak.cumulativeCost} />
        <PeakValue label="Wynik netto" value={peak.netCredits} />
      </View>
    </View>
  );
});

type PeakValueProps = {
  label: string;
  value: number;
};

function PeakValue({ label, value }: PeakValueProps) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    marginHorizontal: 18,
    marginTop: 10,
    padding: 14,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -3,
    marginTop: 7,
  },
  metric: {
    backgroundColor: '#102641',
    borderRadius: 9,
    margin: 3,
    minWidth: '30%',
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  metricLabel: {
    color: boardColors.muted,
    fontSize: 10,
  },
  metricValue: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '800',
    marginTop: 2,
  },
  net: {
    color: '#86efac',
    fontSize: 18,
    fontWeight: '900',
  },
  title: {
    color: boardColors.text,
    flex: 1,
    fontSize: 13,
    fontWeight: '800',
  },
  titleRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
});
