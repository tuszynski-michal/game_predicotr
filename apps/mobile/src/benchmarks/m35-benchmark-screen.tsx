import { useEffect, useState } from 'react';
import {
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  LocalGameConfig,
  LocalLayoutRepository,
  LocalSnapshotDatabase,
} from '@/data/local-layout-repository';

import {
  M35_BENCHMARK_LOG_PREFIX,
  runM35MobileBenchmark,
  type M35MobileBenchmarkReport,
} from './m35-performance';

type Props = {
  database: LocalSnapshotDatabase;
  databaseInitializationMs: number;
  diagnostics: SnapshotDiagnostics;
  game: LocalGameConfig;
  repository: LocalLayoutRepository;
};

type BenchmarkEnvelope = {
  readonly androidVersion: string;
  readonly buildVariant: 'debug' | 'release';
  readonly deviceManufacturer: string;
  readonly deviceModel: string;
  readonly progressIndicatorReadyMs: number;
  readonly report: M35MobileBenchmarkReport;
};

function deviceField(name: string): string {
  const constants = Platform.constants as unknown as Record<string, unknown>;
  const value = constants[name];
  return typeof value === 'string' && value.length > 0 ? value : 'unknown';
}

export function M35BenchmarkScreen({
  database,
  databaseInitializationMs,
  diagnostics,
  game,
  repository,
}: Props) {
  const [result, setResult] = useState<BenchmarkEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const progressStartedAt = performance.now();
    const frame = requestAnimationFrame(() => {
      const progressIndicatorReadyMs =
        Math.round((performance.now() - progressStartedAt) * 10_000) / 10_000;
      void runM35MobileBenchmark(
        database,
        repository,
        game,
        diagnostics,
        databaseInitializationMs,
      )
        .then((report) => {
          const envelope: BenchmarkEnvelope = {
            androidVersion: String(Platform.Version),
            buildVariant: __DEV__ ? 'debug' : 'release',
            deviceManufacturer: deviceField('Manufacturer'),
            deviceModel: deviceField('Model'),
            progressIndicatorReadyMs,
            report,
          };
          console.info(
            `${M35_BENCHMARK_LOG_PREFIX} ${JSON.stringify(envelope)}`,
          );
          if (active) {
            setResult(envelope);
          }
        })
        .catch((benchmarkError: unknown) => {
          const message =
            benchmarkError instanceof Error
              ? benchmarkError.message
              : 'Unknown benchmark error.';
          console.error(`M35_BENCHMARK_ERROR ${message}`);
          if (active) {
            setError(message);
          }
        });
    });
    return () => {
      active = false;
      cancelAnimationFrame(frame);
    };
  }, [database, databaseInitializationMs, diagnostics, game, repository]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>M3.5 — benchmark 500 000</Text>
        {error === null ? null : (
          <View style={styles.errorCard}>
            <Text style={styles.errorTitle}>Benchmark nie powiódł się</Text>
            <Text selectable>{error}</Text>
          </View>
        )}
        {result === null && error === null ? (
          <View style={styles.card}>
            <Text style={styles.heading}>Pomiar w toku…</Text>
            <Text>
              Aplikacja offline wykonuje exact, prefix oraz pięć pełnych cykli
              Target.
            </Text>
          </View>
        ) : null}
        {result === null ? null : (
          <>
            <View style={styles.card}>
              <Text style={styles.heading}>
                {result.deviceManufacturer} {result.deviceModel}
              </Text>
              <Text>Android: {result.androidVersion}</Text>
              <Text>Build: {result.buildVariant}</Text>
              <Text>
                Inicjalizacja: {result.report.databaseInitializationMs} ms
              </Text>
              <Text>
                Wskaźnik postępu: {result.progressIndicatorReadyMs} ms
              </Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.heading}>p95</Text>
              <Text>
                Exact: {result.report.measurements.exactUnique.p95Ms} ms
              </Text>
              <Text>
                Prefix: {result.report.measurements.prefixFiveCells.p95Ms} ms
              </Text>
              <Text>
                SQLite N-1: {result.report.measurements.cyclicRead.p95Ms} ms
              </Text>
              <Text>
                Target JS: {result.report.measurements.targetCalculation.p95Ms}{' '}
                ms
              </Text>
              <Text>
                E2E: {result.report.measurements.targetEndToEnd.p95Ms} ms
              </Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.heading}>Surowy raport</Text>
              <Text selectable style={styles.raw}>
                {JSON.stringify(result, null, 2)}
              </Text>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#d6dfeb',
    borderRadius: 16,
    borderWidth: 1,
    gap: 6,
    padding: 16,
  },
  content: {
    gap: 16,
    padding: 20,
  },
  errorCard: {
    backgroundColor: '#fff1f1',
    borderColor: '#c83737',
    borderRadius: 16,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  errorTitle: {
    color: '#9f2020',
    fontSize: 18,
    fontWeight: '700',
  },
  heading: {
    color: '#102a43',
    fontSize: 18,
    fontWeight: '700',
  },
  raw: {
    fontFamily: Platform.select({
      android: 'monospace',
      default: undefined,
    }),
    fontSize: 11,
  },
  safeArea: {
    backgroundColor: '#f2f6fb',
    flex: 1,
  },
  title: {
    color: '#102a43',
    fontSize: 24,
    fontWeight: '800',
  },
});
