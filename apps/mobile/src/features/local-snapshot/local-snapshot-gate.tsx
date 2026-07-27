import { SQLiteProvider, useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';

import {
  asLocalDataError,
  buildLocalDatabaseName,
  readSnapshotDiagnostics,
  snapshotAssetId,
  snapshotManifest,
  type LocalDataError,
  type SnapshotDiagnostics,
} from '@/data/bundled-snapshot';
import {
  LocalLayoutRepository,
  type LocalGameConfig,
} from '@/data/local-layout-repository';
import { M35BenchmarkScreen } from '@/benchmarks/m35-benchmark-screen';
import { M35_BENCHMARK_RELEASE_VERSION } from '@/benchmarks/m35-performance';
import { GameWorkspaceScreen } from '@/features/board/game-workspace-screen';

import { SnapshotDiagnosticScreen } from './snapshot-diagnostic-screen';

const APPLICATION_STARTED_AT = performance.now();

export function LocalSnapshotGate() {
  const [error, setError] = useState<LocalDataError | null>(null);

  const handleError = useCallback((providerError: Error) => {
    setError(asLocalDataError(providerError));
  }, []);

  if (error !== null) {
    return <SnapshotDiagnosticScreen error={error} diagnostics={null} />;
  }

  return (
    <SQLiteProvider
      assetSource={{ assetId: snapshotAssetId }}
      databaseName={buildLocalDatabaseName(snapshotManifest)}
      onError={handleError}
    >
      <LocalSnapshotContent />
    </SQLiteProvider>
  );
}

function LocalSnapshotContent() {
  const database = useSQLiteContext();
  const [diagnostics, setDiagnostics] = useState<SnapshotDiagnostics | null>(
    null,
  );
  const [games, setGames] = useState<readonly LocalGameConfig[] | null>(null);
  const [repository, setRepository] = useState<LocalLayoutRepository | null>(
    null,
  );
  const [databaseInitializationMs, setDatabaseInitializationMs] = useState<
    number | null
  >(null);
  const [error, setError] = useState<LocalDataError | null>(null);

  useEffect(() => {
    let active = true;

    async function initialize() {
      try {
        const repository = new LocalLayoutRepository(database);
        const [verifiedDiagnostics, gameCatalog] = await Promise.all([
          readSnapshotDiagnostics(database),
          repository.listGames(),
        ]);

        if (active) {
          setRepository(repository);
          setDiagnostics(verifiedDiagnostics);
          setGames(gameCatalog);
          setDatabaseInitializationMs(
            performance.now() - APPLICATION_STARTED_AT,
          );
        }
      } catch (initializationError: unknown) {
        if (active) {
          setError(asLocalDataError(initializationError));
        }
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, [database]);

  if (error !== null) {
    return <SnapshotDiagnosticScreen error={error} diagnostics={null} />;
  }

  if (
    diagnostics === null ||
    games === null ||
    repository === null ||
    databaseInitializationMs === null
  ) {
    return <SnapshotDiagnosticScreen diagnostics={null} error={null} />;
  }
  const benchmarkGame = games[0];
  if (
    diagnostics.releaseVersion === M35_BENCHMARK_RELEASE_VERSION &&
    benchmarkGame !== undefined
  ) {
    return (
      <M35BenchmarkScreen
        database={database}
        databaseInitializationMs={databaseInitializationMs}
        diagnostics={diagnostics}
        game={benchmarkGame}
        repository={repository}
      />
    );
  }
  return (
    <GameWorkspaceScreen
      diagnostics={diagnostics}
      games={games}
      repository={repository}
    />
  );
}
